import argparse
import threading
import time

import pika
import logging
import os

from orthanc_api_client import OrthancApiClient, ResourceType, JobStatus, ResourceNotFound

logger = logging.getLogger(__name__)

class OrthancReplicator:
    '''
    ## Goal
    The Replicator allows to mirror an Orthanc (source) to another (destination):
    - Every instance received in the first Orthanc has to be forwarded to the second one;
    - Every instance deleted from the first Orthanc has to be deleted from the second one.

    ## Challenge
    The challenge comes from the lack of "DeletedInstance" change type in the changes returned by the
    "/changes" API route of Orthanc.

    ## Trick
    There is a lua event called "OnDeletedInstance". So, a lua script configured in the Orthanc source will
    push the orthanc id of every deleted instance to a RabbitMQ broker.
    This lua script will do the same for every instance stored (in a dedicated queue).
    Here comes the Replicator:
    It will consume these RabbitMQ messages to delete ("to-delete-queue") the instances from the destination
    or to forward ("to-forward-queue") the instances from the source to the destination.

    ## How it works
    ### On the source side
    There is a lua script to configure (see dedicated sample TODO: add url).
    Basically, this lua script should push messages to the broker (rabbitmq) following these rules:
    - vhost: "/" (default one)
    - exchange: "orthanc-exchange"
    - queue for instances to delete: "to-delete-queue"
    - queue for instances to forward: "to-forward-queue"

    Side note: these hardcoded names could be made configurable in a further version...

    ### Broker
    RabbitMQ has to be up and running.

    ### Replicator
    The replicator needs to connect to both Orthanc (source and destination) and to RabbitMQ.
    So these information should be provided:
    source_url: Orthanc source url
    source_user: Orthanc source user name
    source_pwd: Orthanc source password
    dest_url: Orthanc destination url
    dest_user: Orthanc destination user name
    dest_pwd: Orthanc destination password
    broker_url: Broker url
    broker_user: Broker user name
    broker_pwd: Broker password
    broker_port: Broker port nr
    '''

    def __init__(self,
                 source: OrthancApiClient,
                 destination: OrthancApiClient,
                 broker_params: pika.ConnectionParameters
        ):

        self._source = source
        self._destination = destination
        self._broker_params = broker_params
        self._consuming_thread = None

        self._stop_requested = False

    def to_delete_callback(self, channel, method, properties, body):
        orthanc_id = body.decode('utf8')
        try:
            self._destination.instances.delete(orthanc_id)
            channel.basic_ack(delivery_tag=method.delivery_tag)
            logger.debug(f"Deleted instance from destination ({orthanc_id}).")
            return

        except ResourceNotFound as ex:
            # The instance may have been deleted (by a user, a script,...) from the destination between the moment
            # it has been deleted from the source (and the id pushed into rabbitmq)
            # and the moment we try to handle it. So, the destination will return a 404 http error.
            # In this case, simply log the error and ack the message (don't raise the Exception)
            logger.info(f"Unable (404) to delete instance from destination ({orthanc_id}), probably already deleted...")
            channel.basic_ack(delivery_tag=method.delivery_tag)

        except Exception as ex:
            logger.warning(f"Unable to delete instance from destination ({orthanc_id}), requeueing...")
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def to_forward_callback(self, channel, method, properties, body):
        orthanc_id = body.decode('utf8')
        try:
            dicom = self._source.instances.get_file(orthanc_id)

        except ResourceNotFound as ex:
            # The instance may have been deleted (by a user, a script,...) from the source between the moment
            # it has been received in the source (and the id pushed into rabbitmq)
            # and the moment we try to handle it. So, the source will return a 404 http error.
            # In this case, simply log the error and ack the message (don't raise the Exception)
            logger.warning(f"Unable (404) to get instance instance from source ({orthanc_id}), probably already deleted...")
            channel.basic_ack(delivery_tag=method.delivery_tag)
            return
        except Exception as ex:
            logger.warning(f"Unable to get instance from source ({orthanc_id}), requeueing...")
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return

        try:
            self._destination.upload(dicom)

            channel.basic_ack(delivery_tag=method.delivery_tag)
            logger.debug(f"Forwarded instance to destination ({orthanc_id}).")
            return

        except Exception as ex:
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            logger.warning(f"Unable to upload instance to destination ({orthanc_id}), requeueing...")
            return

    def wait_orthanc_started(self):
        retry = 0
        while not self._source.is_alive():
            logger.info("Waiting to connect to Orthanc source")
            retry += 1
            if retry == 5:
                logger.error("Could not connect to Orthanc at startup")
                raise Exception("Could not connect to Orthanc at startup")
            time.sleep(1)

        retry = 0
        while not self._destination.is_alive():
            logger.info("Waiting to connect to Orthanc destination")
            retry += 1
            if retry == 5:
                logger.error("Could not connect to Orthanc at startup")
                raise Exception("Could not connect to Orthanc at startup")
            time.sleep(1)


    def _consume(self):
        logger.info("----- Initializing Orthanc Replicator...")

        # TODO: allow multithreading?
        # see https://blog.boot.dev/python/using-concurrent-subscribers-rabbitmq-in-python-pika/

        self.wait_orthanc_started()

        # we want the replicator to retry to connect to the broker if there is a trouble...
        while not self._stop_requested:
            try:

                # initialize connection to rabbitmq
                connection = pika.BlockingConnection(self._broker_params)
                channel = connection.channel()

                # These steps should have been done in the lua, but they are idempotent
                channel.exchange_declare(exchange="orthanc-exchange", exchange_type="direct", durable=True)

                # "Main" queues
                channel.queue_declare(queue='to-forward-queue',
                                      durable=True,
                                      arguments={
                                          'x-dead-letter-exchange': 'orthanc-exchange',
                                          'x-dead-letter-routing-key': 'standby-forward-queue'
                                      })
                channel.queue_declare(queue='to-delete-queue', durable=True,
                                      arguments={
                                          'x-dead-letter-exchange': 'orthanc-exchange',
                                          'x-dead-letter-routing-key': 'standby-delete-queue'
                                      })

                # "Standby" queues (messages are waiting there is they were nacked)
                channel.queue_declare(queue='standby-delete-queue', durable=True,
                                      arguments={
                                          'x-message-ttl': 10000,
                                          'x-dead-letter-exchange': 'orthanc-exchange',
                                          'x-dead-letter-routing-key': 'to-delete-queue'
                                      })
                channel.queue_declare(queue='standby-forward-queue', durable=True,
                                      arguments={
                                          'x-message-ttl': 10000,
                                          'x-dead-letter-exchange': 'orthanc-exchange',
                                          'x-dead-letter-routing-key': 'to-forward-queue'
                                      })

                channel.queue_bind(exchange="orthanc-exchange", queue="to-forward-queue", routing_key="to-forward-queue")
                channel.queue_bind(exchange="orthanc-exchange", queue="to-delete-queue", routing_key="to-delete-queue")
                channel.queue_bind(exchange="orthanc-exchange", queue="standby-delete-queue", routing_key="standby-delete-queue")
                channel.queue_bind(exchange="orthanc-exchange", queue="standby-forward-queue", routing_key="standby-forward-queue")

                channel.basic_consume(queue='to-forward-queue', on_message_callback=self.to_forward_callback)
                channel.basic_consume(queue='to-delete-queue', on_message_callback=self.to_delete_callback)

                # we declare a "stop-queue" which allows to gracefully stop the connection with rabbitmq
                channel.queue_declare(queue='stop-queue')
                channel.queue_bind(exchange="orthanc-exchange", queue="stop-queue", routing_key="stop-queue")
                channel.basic_consume(queue='stop-queue', on_message_callback=self.stop_callback, auto_ack=True)

                logger.info("Broker connection configured, waiting for messages...")
                channel.start_consuming() # this never ends

                channel.stop_consuming()
                connection.close()

            except Exception as e:
                logger.info("Broker consuming error, will retry soon...")
                time.sleep(1)

    def stop_callback(self, channel, method, properties, body):
        channel.stop_consuming()
        channel.close()

        logger.info("Broker connection stop requested...")

    def stop(self):
        logger.info("Stopping Replicator...")
        self._stop_requested = True

        connection = pika.BlockingConnection(self._broker_params)
        channel = connection.channel()

        channel.basic_publish(exchange='orthanc-exchange', routing_key='stop-queue', body="stop")

        connection.close()

    def execute(self):
        self._consuming_thread = threading.Thread(target=self._consume)
        self._consuming_thread.start()

# example:
# python orthanc_tools/orthanc_replicator.py --source_url=http://localhost:8042 --dest_url=http://localhost:8044 --broker_url=http://localhost


if __name__ == '__main__':
    level = logging.INFO

    if os.environ.get('VERBOSE_ENABLED'):
        level = logging.DEBUG

    logging.basicConfig(level=level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    parser = argparse.ArgumentParser(description='Replicates the content of an Orthanc into another Orthanc')
    parser.add_argument('--source_url', type=str, default=None, help='Orthanc source url')
    parser.add_argument('--source_user', type=str, default=None, help='Orthanc source user name')
    parser.add_argument('--source_pwd', type=str, default=None, help='Orthanc source password')
    parser.add_argument('--source_api_key', type=str, default=None, help='Orthanc source api-key')
    parser.add_argument('--dest_url', type=str, default=None, help='Orthanc destination url')
    parser.add_argument('--dest_user', type=str, default=None, help='Orthanc destination user name')
    parser.add_argument('--dest_pwd', type=str, default=None, help='Orthanc destination password')
    parser.add_argument('--dest_api_key', type=str, default=None, help='Orthanc destination api-key')
    parser.add_argument('--broker_url', type=str, default='broker', help='Broker url')
    parser.add_argument('--broker_user', type=str, default='rabbit', help='Broker user name')
    parser.add_argument('--broker_pwd', type=str, default='123456', help='Broker password')
    parser.add_argument('--broker_port', type=int, default=5672, help='Broker port nr')
    #parser.add_argument('--worker_threads_count', type=int, default=1, help='Number of worker threads')

    args = parser.parse_args()

    source_url = os.environ.get("SOURCE_URL", args.source_url)
    source_user = os.environ.get("SOURCE_USER", args.source_user)
    source_pwd = os.environ.get("SOURCE_PWD", args.source_pwd)
    source_api_key = os.environ.get("SOURCE_API_KEY", args.source_api_key)
    
    dest_url = os.environ.get("DEST_URL", args.dest_url)
    dest_user = os.environ.get("DEST_USER", args.dest_user)
    dest_pwd = os.environ.get("DEST_PWD", args.dest_pwd)
    dest_api_key = os.environ.get("DEST_API_KEY", args.dest_api_key)
    
    broker_url = os.environ.get("BROKER_URL", args.broker_url)
    broker_user = os.environ.get("BROKER_USER", args.broker_user)
    broker_pwd = os.environ.get("BROKER_PWD", args.broker_pwd)
    broker_port = int(os.environ.get("BROKER_PORT", args.broker_port))
    
    #worker_threads_count = int(os.environ.get("WORKER_THREADS_COUNT", str(args.worker_threads_count)))

    broker_connection_parameters = pika.ConnectionParameters(broker_url, broker_port, credentials=pika.PlainCredentials(broker_user, broker_pwd))

    destination = None
    if dest_api_key is not None:
        destination=OrthancApiClient(dest_url, headers={"api-key":dest_api_key})
    else:
        destination=OrthancApiClient(dest_url, user=dest_user, pwd=dest_pwd)
    
    source = None
    if source_api_key is not None:
        source=OrthancApiClient(source_url, headers={"api-key":source_api_key})
    else:
        source=OrthancApiClient(source_url, user=source_user, pwd=source_pwd)


    replicator = OrthancReplicator(
        source=source,
        destination=destination,
        broker_params=broker_connection_parameters
    )

    replicator.execute()



