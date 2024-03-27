import datetime
import socket
from socketserver import ThreadingTCPServer, BaseRequestHandler
from typing import Dict
import pytz

import httpx
import structlog
from dateutil.tz import tz
from elgas import utils, frames, constants
from elgas.client import ElgasClient
from elgas.security import EncryptionKeyId
from elgas.transport import BlockingTcpTransport
from elgas.application import CallRequest, ReadArchiveByTimeResponse, ReadArchiveResponse, Archive
import attr
import click

from elgas.utils import bytes_to_datetime

import settings

LOG = structlog.get_logger()

HOST = "0.0.0.0"
PORT = 8889


def now() -> datetime.datetime:
    return datetime.datetime.utcnow().replace(tzinfo=pytz.utc)


class ESMPError(Exception):
    "An error with Utilitarian ESMP"


@attr.s(auto_attribs=True)
class BlockingTcpServerTransport(BlockingTcpTransport):
    """
    Subclass so that `connect` does nothing as we want to put in an already connected socket.
    """

    def connect(self):
        pass


def to_meter_standard_time(dt: datetime, meter_tz: datetime.tzinfo) -> datetime:
    """
    Convert a timestamp in meters local time to meter standard time.
    Remove the tzinfo so that it is not treated as an aware object
    Request must be in standard time.
    """
    meter_time = dt.astimezone(meter_tz)
    standard_time = meter_time - meter_time.dst()
    standard_time = standard_time.replace(tzinfo=None)
    return standard_time


class ElgasCallToDispatchingHandler(BaseRequestHandler):

    def create_elgas_client(self, password_id: int, password: str, encryption_key_id: int,
                            encryption_key: str, ) -> ElgasClient:
        transport = BlockingTcpServerTransport(host=self.client_address[0], port=self.client_address[1], timeout=30)
        transport.tcp_socket = self.request
        client = ElgasClient(
            transport=transport,
            password=password,
            password_id=password_id,
            encryption_key=bytes.fromhex(encryption_key),
            encryption_key_id=EncryptionKeyId(encryption_key_id),
        )

        return client

    def handle(self):
        host, port = self.client_address
        structlog.contextvars.bind_contextvars(peer_address=self.client_address)
        LOG.info("Handling TCP stream")

        data = self.request.recv(1024)

        LOG.debug(
            f"Received TCP data",
            data=data,
        )

        escaped_data = utils.return_characters(data)
        LOG.debug(f"Received TCP data and de-escaped it", data=escaped_data)

        # Try to load as Elgas Request
        request = frames.Request.from_bytes(escaped_data)

        LOG.info(f"Received ELGAS request", request=request)

        if request.service != constants.ServiceNumber.CALL:
            LOG.info(
                "Request is not call from device. Closing stream",
            )
            self.request.shutdown(socket.SHUT_RDWR)
            self.request.close()
            return

        call_request = CallRequest.from_bytes(request.data)

        LOG.info(
            f"Received CALL APDU",
            serial_number=call_request.serial_number,
            call_request=call_request,
        )
        structlog.contextvars.bind_contextvars(device_serial_number=call_request.serial_number,
                                               station_id=call_request.station_id)

        # Respond to device with an empty response.
        response = frames.Response(
            service=constants.ServiceNumber.CALL,
            destination_address_1=request.source_address_1,
            destination_address_2=request.source_address_2,
            source_address_1=request.destination_address_1,
            source_address_2=request.destination_address_2,
            data=b"",
        )
        self.request.sendall(utils.escape_characters(response.to_bytes()))
        LOG.info(f"ACKed CALL Request")

        readout_settings = self.get_readout_settings(call_request.serial_number)

        meter_timezone = tz.gettz(readout_settings["meter_timezone"])

        record_length = readout_settings["archive_record_length"]

        elgas_client = self.create_elgas_client(password_id=readout_settings["password_id"],
                                                password=readout_settings["password"],
                                                encryption_key_id=readout_settings["encryption_key_id"],
                                                encryption_key=readout_settings["encryption_key"])

        LOG.info("Created ELGAS Client", client=elgas_client)

        elgas_client.connect()
        oldest_timestamp = datetime.datetime.fromisoformat(readout_settings["oldest_timestamp"])
        meter_local_oldest_timestamp = to_meter_standard_time(oldest_timestamp, meter_timezone)

        if readout_settings["read_until_timestamp"]:
            newest_timestamp = datetime.datetime.fromisoformat(readout_settings["read_until_timestamp"])
        else:
            newest_timestamp = now()
        meter_local_newest_timestamp = to_meter_standard_time(newest_timestamp, meter_timezone)

        readout_result = self.read_archive(client=elgas_client,
                                           oldest_timestamp=meter_local_oldest_timestamp,
                                           newest_timestamp=meter_local_newest_timestamp,
                                           read_amount=readout_settings["amount_to_read"],
                                           record_length=record_length,
                                           archive=Archive(readout_settings["archive"])
                                           )
        LOG.info("Finished reading archive", client=elgas_client, total_amount_of_data=len(readout_result))


        # TODO: add sentry

    def read_archive(self, client: ElgasClient, archive: Archive, oldest_timestamp: datetime,
                     newest_timestamp: datetime, read_amount: int, record_length: int):

        LOG.info(
            "Reading archive",
            oldest_timestamp=oldest_timestamp,
            newest_timestamp=newest_timestamp,
            archive=archive,
            amount=read_amount,
        )
        read_result = list()
        total_data = b""
        end_of_data = False
        read_from_record = None
        while not end_of_data:
            if read_from_record is None:
                # read by time the first time.

                LOG.info(
                    "Reading archive part",
                    oldest_timestamp=oldest_timestamp,
                    archive=archive,
                    amount=read_amount,
                )
                result: ReadArchiveByTimeResponse = client.read_archive_by_time(
                    amount=read_amount,
                    archive=archive,
                    oldest_timestamp=oldest_timestamp,
                )

            else:
                # the remaining reads is done via record_id
                LOG.info(
                    "Reading Archive",
                    oldest_record_id=read_from_record,
                    archive=archive,
                    amount=read_amount,
                )
                result: ReadArchiveResponse = client.read_archive(
                    amount=read_amount,
                    archive=archive,
                    oldest_record_id=read_from_record,
                )
            received_data = result.data
            total_data += result.data
            number_of_records = len(result.data) / record_length

            records = list()
            for _ in range(0, int(number_of_records)):
                records.append(received_data[: record_length])
                data = received_data[record_length:]

            timestamps = list()
            for record in records:
                bcd_timestamp_data = record[4:10]
                timestamp, _, _ = bytes_to_datetime(bcd_timestamp_data)
                timestamps.append(timestamp)

            LOG.info(
                "Received archive data",
                archive=archive,
                data_length=len(result.data),
                record_amount=number_of_records
            )

            read_from_record = result.oldest_record_id + read_amount

            if number_of_records < read_amount:
                # If we read fewer records than we requested we are at the end of the data
                LOG.info("Number of records is lower than requested. End if data reached, Stopping readout.")
                end_of_data = True
            if any([newest_timestamp <= timestamp for timestamp in timestamps]):
                # We have read until the required timestamp
                LOG.info(
                    "Timestamp larger or equal to newest timestamp requested found in archive "
                    "readout. Stopping readout")
                end_of_data = True

            return total_data

    def get_readout_settings(self, serial_number: int) -> Dict:
        url = f"{settings.UTILITARIAN_BASE_URL}/v1/metering/edge/elgas/readout-settings/{serial_number}"
        headers = {"Authorization": f"Token {settings.UTILITARIAN_API_KEY}"}
        LOG.info("Requesting readout settings from ESMP", url=url)
        response = httpx.get(url, headers=headers)
        if response.status_code == 200:
            LOG.info("Successfully retrieved readout settings from ESMP")
            return response.json()
        else:
            LOG.info("Failed to retrieve readout settings", http_status_code=response.status_code,
                     response=response.content)
            raise ESMPError("Not able to fetch readout settings")



@click.command()
@click.option("--host", default=None, help="Host to serve the application")
@click.option("--port", type=int, default=None, help="Port to serve the application")
def start_server(host, port):
    """ """

    request_handler = ElgasCallToDispatchingHandler
    if host is None:
        serve_host = settings.HOST
    else:
        serve_host = host

    if port is None:
        serve_port = settings.PORT
    else:
        serve_port = port
    with ThreadingTCPServer((serve_host, serve_port), request_handler) as server:
        LOG.info("Starting ELGAS server", host=serve_host, port=serve_port, request_handler=request_handler.__name__)
        server.serve_forever()


if __name__ == "__main__":
    start_server()
