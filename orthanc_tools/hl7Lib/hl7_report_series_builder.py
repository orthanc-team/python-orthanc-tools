import typing
import tempfile
import base64


class ReportSeriesBuilder:

    def __init__(self, orthanc_client: 'OrthancApiClient', series_name: str = "Report"):
        """
        orthanc_client: a well configured orthancClient, must contain the study to attach the pdf to
        series_name: the SeriesDescription of the series which will contain the pdf

        """
        self._orthanc_client = orthanc_client
        self._series_name = series_name

    def generate(self, values: typing.Dict[str, str]) -> str:
        """
        This will extract the pdf from the base64 string,
        search for the study base on the StudyInstanceUID and then
        attach the pdf to this study.

        values: dict with these values: Base64Report, StudyInstanceUID, PatientName

        returns the instance_id of the created instance
        """

        # TODO: refactor not to use a temporary file but only memory buffers

        with tempfile.NamedTemporaryFile() as f:
            # let's build the pdf from the base64 encoded field
            f.write(base64.decodebytes(bytes(values["Base64Report"], "utf-8")))

            # let's find the study to attach the pdf to
            study_id = self._orthanc_client.studies.lookup(values["StudyInstanceUID"])
            if study_id is None:
                raise Exception(f"Unable to find the study to attach the report to ({values['PatientName']} - {values['StudyInstanceUID']})")
            else:
                # let's attach the pdf to the study
                self._orthanc_client.studies.attach_pdf(study_id, f.name, self._series_name)