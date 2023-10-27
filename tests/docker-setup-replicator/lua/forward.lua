-- This script pushes some events to a broker (rabbitmq)

brokerUser = ""
brokerPassword = ""

function Initialize()

    -- at starting, let's create some rabbitmq stuff (these actions are idempotent)
    local header = {
        ["content-type"] = "application/json",
        ["expect"] = ""
    }

    brokerUser = os.getenv("BROKER_USER")
    brokerPassword = os.getenv("BROKER_PASSWORD")

    SetHttpCredentials(brokerUser, brokerPassword)
    SetHttpTimeout(1)

    -- let's begin with the exchange
    local payload = {}
    payload["type"] = "direct"
    payload["durable"] = true

    -- "%2F" is for "/" char which is the default vhost name in RabbitMQ
    HttpPut("http://broker:15672/api/exchanges/%2f/orthanc-exchange", DumpJson(payload, false), header)


    --let's create the queues
    payload = {}
    payload["auto_delete"] = false
    payload["durable"] = true
    payload["arguments"] = {["x-dead-letter-exchange"] = "orthanc-exchange", ["x-dead-letter-routing-key"] = "standby-delete-queue"}

    HttpPut("http://broker:15672/api/queues/%2F/to-delete-queue/", DumpJson(payload, false), header)

    payload = {}
    payload["auto_delete"] = false
    payload["durable"] = true
    payload["arguments"] = {["x-dead-letter-exchange"] = "orthanc-exchange", ["x-dead-letter-routing-key"] = "standby-forward-queue"}
    HttpPut("http://broker:15672/api/queues/%2F/to-forward-queue/", DumpJson(payload, false), header)

    -- let's bind these queues to the exchange
    payload = {}
    payload["routing_key"] = "to-delete-queue"
    HttpPost("http://broker:15672/api/bindings/%2F/e/orthanc-exchange/q/to-delete-queue/", DumpJson(payload, false), header)

    payload = {}
    payload["routing_key"] = "to-forward-queue"
    HttpPost("http://broker:15672/api/bindings/%2F/e/orthanc-exchange/q/to-forward-queue/", DumpJson(payload, false), header)

    -- TODO: create the standby-queues here?


end


function OnDeletedInstance(instanceId)
    PublishEvent(instanceId, "to-delete-queue")
end


function OnStoredInstance(instanceId, tags, metadata)
    PublishEvent(instanceId, "to-forward-queue")
end


function PublishEvent(instanceId, queueName)
    local payload = {}

    local delivery_mode = 2 -- 2 is the value for persistent delivery_mode

    payload["properties"] = {["content-type"] = "application/json", ["delivery_mode"] = delivery_mode}
    payload["routing_key"] = queueName
    payload["payload"] = instanceId
    payload["payload_encoding"] = "string"

    local header = {
        ["content-type"] = "application/json",
        ["expect"] = ""
    }

    SetHttpCredentials(brokerUser, brokerPassword)
    SetHttpTimeout(1)

    -- double '/' is because the default name of the exchange is an empty string
    HttpPost("http://broker:15672/api/exchanges/%2F/orthanc-exchange/publish", DumpJson(payload, false), header)

end

