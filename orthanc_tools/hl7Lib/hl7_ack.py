from datetime import datetime
import random
from typing import Optional, Union

import hl7


def _escape_hl7_text(value: str) -> str:
    return (
        value.replace("\\", "\\E\\")
        .replace("|", "\\F\\")
        .replace("^", "\\S\\")
        .replace("~", "\\R\\")
        .replace("&", "\\T\\")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def build_acknowledgement(
    request: Union[str, hl7.Message],
    status: str,
    error_description: Optional[str] = None,
) -> hl7.Message:
    if status not in {"AA", "AE", "AR"}:
        raise ValueError(f"Unsupported HL7 acknowledgment status: {status}")

    hl7_request = request if isinstance(request, hl7.Message) else hl7.parse(request)
    trigger_event = str(hl7_request["MSH.F9.R1.C2"]) or "O01"

    msh = (
        "MSH|^~\\&|{sending_application}||{receiving_application}|"
        "{receiving_facility}|{date_time}||ACK^{trigger_event}|"
        "{ack_message_id}|P|2.3||||||8859/1"
    ).format(
        sending_application=hl7_request["MSH.F5.R1.C1"],
        receiving_application=hl7_request["MSH.F3.R1.C1"],
        receiving_facility=hl7_request["MSH.F4.R1.C1"],
        date_time=datetime.now().strftime("%Y%m%d%H%M%S"),
        trigger_event=trigger_event,
        ack_message_id=str(random.randrange(0, 10**15)),
    )
    msa = f"MSA|{status}|{hl7_request['MSH.F10.R1.C1']}"
    if error_description:
        msa += f"|{_escape_hl7_text(str(error_description))}"

    return hl7.parse(f"{msh}\r{msa}")
