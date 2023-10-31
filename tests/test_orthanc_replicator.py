import time
import subprocess
from orthanc_api_client import OrthancApiClient, helpers
import pathlib
import logging
import unittest
import pika

from orthanc_tools import OrthancReplicator

here = pathlib.Path(__file__).parent.resolve()

logger = logging.getLogger('orthanc_tools')
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)


class TestOrthancReplicator(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        subprocess.run(["docker", "compose", "down", "-v"], cwd=here/"docker-setup-replicator")
        subprocess.run(["docker", "compose", "up", "-d"], cwd=here/"docker-setup-replicator")

        cls.oa = OrthancApiClient('http://localhost:10042', user='test', pwd='test')
        cls.oa.wait_started()
        cls.ob = OrthancApiClient('http://localhost:10043', user='test', pwd='test')
        cls.ob.wait_started()

    @classmethod
    def tearDownClass(cls):
        subprocess.run(["docker", "compose", "down", "-v"], cwd=here/"docker-setup-replicator")

    def get_rabbitmq_connection_params(self):
        broker_connection_parameters = pika.ConnectionParameters(
            "localhost", 5672,
            credentials=pika.PlainCredentials("rabbit", "123456"),
            connection_attempts=3,
            heartbeat=300,
            socket_timeout=None,
            stack_timeout=None,
            blocked_connection_timeout=None
        )
        return broker_connection_parameters

    def get_queue_length(self, queue: str, standby: bool):
        pika_conn_params = self.get_rabbitmq_connection_params()
        connection = pika.BlockingConnection(pika_conn_params)
        channel = connection.channel()

        # only way to interact with a queue: declare it again
        # this is idempotent and the existing messages are not affected
        if standby:
            queue_name = f"standby-{queue}-queue"
            routing_key = f"to-{queue}-queue"
            arguments = {
                'x-message-ttl': 10000,
                'x-dead-letter-exchange': 'orthanc-exchange',
                'x-dead-letter-routing-key': routing_key
            }
        else:
            queue_name = f"to-{queue}-queue"
            routing_key = f"standby-{queue}-queue"
            arguments = {
                'x-dead-letter-exchange': 'orthanc-exchange',
                'x-dead-letter-routing-key': routing_key
            }

        queue_to_count = channel.queue_declare(queue=queue_name, durable=True, arguments=arguments)
        connection.close()
        return queue_to_count.method.message_count

    def purge_all_queues(self):
        pika_conn_params = self.get_rabbitmq_connection_params()
        connection = pika.BlockingConnection(pika_conn_params)
        channel = connection.channel()

        # we do nothing in catch because the queue could be not existing which is not a problem
        try:
            channel.queue_purge(queue='to-delete-queue')
        except:
            pass
        try:
            channel.queue_purge(queue='to-forward-queue')
        except:
            pass
        try:
            channel.queue_purge(queue='standby-delete-queue')
        except:
            pass
        try:
            channel.queue_purge(queue='standby-forward-queue')
        except:
            pass

        connection.close()

    def get_number_of_running_containers(self):
        bash_cmd = "docker ps | tail -n +2 | wc -l"
        running_containers = int(subprocess.check_output(bash_cmd, shell=True))
        return running_containers

    def test_forward_and_delete_instance(self):

        # clean up
        self.oa.delete_all_content()
        self.ob.delete_all_content()
        self.purge_all_queues()

        # upload an instance
        self.oa.upload_file(here / "stimuli/CT_small.dcm")

        # let's configure the replicator
        broker_connection_parameters = self.get_rabbitmq_connection_params()
        replicator = OrthancReplicator(
            source=self.oa,
            destination=self.ob,
            broker_params=broker_connection_parameters
        )

        replicator.execute()

        # wait until the instance has been forwarded to the destination
        helpers.wait_until(lambda: len(self.ob.studies.get_all_ids()) == 1, 5)

        # Let's check that there is now an instance in the destination
        self.assertEqual(len(self.oa.instances.get_all_ids()), len(self.ob.instances.get_all_ids()))

        # Let's remove the instance from the source
        self.oa.delete_all_content()

        # and check that is has been deleted from the destination
        helpers.wait_until(lambda: len(self.ob.studies.get_all_ids()) == 1, 5)
        self.assertEqual(len(self.oa.instances.get_all_ids()), len(self.ob.instances.get_all_ids()))

        replicator.stop()

    def test_retry_if_upload_fails(self):
        self.oa.delete_all_content()
        self.ob.delete_all_content()
        self.purge_all_queues()

        broker_connection_parameters = self.get_rabbitmq_connection_params()
        replicator = OrthancReplicator(
            source=self.oa,
            destination=self.ob,
            broker_params=broker_connection_parameters
        )

        replicator.execute()

        # let's inhibit the destination, so that the replicator won't be able to forward the instance we will upload
        with open(here / "docker-setup-replicator/inhibit.lua", 'rb') as f:
            lua_script = f.read()
        self.ob.execute_lua_script(lua_script)

        self.oa.upload_file(here / "stimuli/CT_small.dcm")

        # let's check until the message is in the standby queue
        helpers.wait_until(lambda: self.get_queue_length("forward", True) == 1, 5)

        # let's uninhibit the destination

        with open(here / "docker-setup-replicator/uninhibit.lua", 'rb') as f:
            lua_script = f.read()
        self.ob.execute_lua_script(lua_script)

        # Let's check that there is now an instance in the destination
        helpers.wait_until(lambda: len(self.ob.studies.get_all_ids()) == 1, 12)
        self.assertEqual(len(self.oa.instances.get_all_ids()), len(self.ob.instances.get_all_ids()))

        replicator.stop()

    def test_already_deleted_instance(self):
        self.oa.delete_all_content()
        self.ob.delete_all_content()
        self.purge_all_queues()

        broker_connection_parameters = self.get_rabbitmq_connection_params()
        replicator = OrthancReplicator(
            source=self.oa,
            destination=self.ob,
            broker_params=broker_connection_parameters
        )

        replicator.execute()

        # let's upload an instance in the source
        self.oa.upload_file(here / "stimuli/CT_small.dcm")

        # wait until it has been forwarded to the destination
        helpers.wait_until(lambda: len(self.ob.studies.get_all_ids()) == 1, 5)

        # remove it from the destination...
        self.ob.delete_all_content()

        # ...and from the source
        self.oa.delete_all_content()

        # the Replicator shouldn't retry the deletion from the destination,
        # so let's check that the queues are empty
        helpers.wait_until(lambda: self.get_queue_length("delete", False) == 0, 5)
        helpers.wait_until(lambda: self.get_queue_length("delete", True) == 0, 5)

        replicator.stop()

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    unittest.main()

