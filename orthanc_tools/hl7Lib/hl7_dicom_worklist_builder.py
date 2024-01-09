import os
import typing
import pydicom
from enum import Enum


class DicomElementType(Enum):
    MANDATORY = 1  # for dicom tags that must be there (type 1 or 1c) -> throw an exception if not present
    REQUIRED = 2  # for dicom tags that are mandatory but accepts null value (type 2 or 2c)
    OPTIONAL = 3  # for dicom tags that are not mandatory (type 3)


class DicomWorklistBuilder:

    def __init__(self, folder: str = None):
        self._folder = folder

    def get_folder(self):
        return self._folder

    # to override in derived class to customize the workilist before it is saved to disk
    def customize(self, ds: pydicom.dataset.FileDataset) -> pydicom.dataset.FileDataset:
        return ds

    def generate(self, values: typing.Dict[str, str], file_name: str = None) -> str:
        """

        :param values: a Dictionary object created from an HL7 message.  Keys of the dico shall match pydicom tag names (i.e: AccessionNumber, PatientID, ...)
        :param filename:
        :return: the filename created
        """
        assert self._folder is not None or file_name is not None, "Please always provide a folder when creating the builder or provide a filename each time you generate a worklist"

        # now, let's try to build a DWL out of this
        file_meta = pydicom.dataset.Dataset()
        file_meta.MediaStorageSOPClassUID = '1.2.276.0.7230010.3.1.0.1'  # shall we use 1.2.840.10008.5.1.4.31 ?
        file_meta.MediaStorageSOPInstanceUID = pydicom.uid.generate_uid()
        file_meta.ImplementationClassUID = '1.2.826.0.1.3680043.9.6676.1.0.0.1'  # 1.2.826.0.1.3680043.9.6676. is Osimis prefix
        file_meta.ImplementationVersionName = 'OSIMISHL7DWL'

        ds = pydicom.dataset.FileDataset(file_name, {}, file_meta = file_meta, preamble = b'\0' * 128)
        if not "SOPInstanceUID" in values:
            values["SOPInstanceUID"] = pydicom.uid.generate_uid()
        if not "StudyInstanceUID" in values:
            values["StudyInstanceUID"] = pydicom.uid.generate_uid()  # set a default StudyInstanceUID.  It might be overriden from the dwl object

        # clip patient address at 64 chars (one of the Avignon CT does not handle them)
        patient_address = values.get('PatientAddress')
        if patient_address and len(patient_address) > 64:
            patient_address = patient_address[:60] + "..."
            values['PatientAddress'] = patient_address

        for field_name, element_type in [('AccessionNumber', DicomElementType.REQUIRED),
                                        ('InstitutionName', DicomElementType.OPTIONAL),
                                        ('InstitutionAddress', DicomElementType.OPTIONAL),
                                        ('PatientID', DicomElementType.MANDATORY),
                                        ('OtherPatientIDs', DicomElementType.OPTIONAL),
                                        ('IssuerOfPatientID', DicomElementType.OPTIONAL),
                                        ('PatientName', DicomElementType.MANDATORY),
                                        ('PatientMotherBirthName', DicomElementType.OPTIONAL),
                                        ('PatientAddress', DicomElementType.OPTIONAL),
                                        ('PatientBirthDate', DicomElementType.MANDATORY),
                                        ('PatientSex', DicomElementType.MANDATORY),
                                        ('SOPInstanceUID', DicomElementType.MANDATORY),
                                        ('StudyInstanceUID', DicomElementType.MANDATORY),
                                        ('RequestingPhysician', DicomElementType.REQUIRED),
                                        ('ReferringPhysicianName', DicomElementType.REQUIRED),
                                        ('RequestedProcedureDescription', DicomElementType.REQUIRED),
                                        ('RequestedProcedureID', DicomElementType.MANDATORY),
                                        ('SpecificCharacterSet', DicomElementType.MANDATORY),
                                        ('ConfidentialityConstraintOnPatientDataDescription', DicomElementType.OPTIONAL),
                                        ('PatientWeight', DicomElementType.OPTIONAL),
                                        ('PatientSpeciesDescription', DicomElementType.OPTIONAL),
                                        ('PatientBreedDescription', DicomElementType.OPTIONAL),
                                        ('ResponsiblePerson', DicomElementType.OPTIONAL),
                                        ('PatientSexNeutered', DicomElementType.OPTIONAL)
                          ]:
            self._add_field(ds, values, field_name, element_type)

        ds.ReferencedStudySequence = pydicom.sequence.Sequence()
        ds.ReferencedPatientSequence = pydicom.sequence.Sequence()

        step = pydicom.dataset.Dataset()
        step.ScheduledProcedureStepDescription = values.get('RequestedProcedureDescription')
        for field_name, element_type in [('Modality', DicomElementType.REQUIRED),
                                        ('ScheduledProcedureStepStartDate', DicomElementType.OPTIONAL),
                                        ('ScheduledProcedureStepStartTime', DicomElementType.OPTIONAL),
                                        ('ReasonForTheRequestedProcedure', DicomElementType.OPTIONAL),
                                        ('ReferringPhysicianName', DicomElementType.REQUIRED),
                                        ('ScheduledStationAETitle', DicomElementType.MANDATORY),
                                        ('ScheduledPerformingPhysicianName', DicomElementType.REQUIRED),
                                        ('ScheduledProcedureStepID', DicomElementType.MANDATORY),
                                        ('ScheduledStationName', DicomElementType.REQUIRED),
                                        ]:
            self._add_field(step, values, field_name, element_type)

        ds.ScheduledProcedureStepSequence = pydicom.sequence.Sequence([step])

        ds = self.customize(ds)

        if file_name is None:  # if no filename provided, save in the folder
            file_name = os.path.join(self._folder, "{id}.wl".format(id = ds.AccessionNumber))

        ds.save_as(file_name, write_like_original = False)
        return file_name

    def _add_field(self, ds: pydicom.dataset.Dataset, values: typing.Dict[str, str], field_name: str, element_type: DicomElementType):
        if field_name in values:
            if values[field_name] is not None:
                ds.__setattr__(field_name, values.get(field_name))
            elif element_type == DicomElementType.REQUIRED:
                ds.__setattr__(field_name, '')
            elif element_type == DicomElementType.MANDATORY:
                raise Exception("missing field '{fieldName}'".format(fieldName = field_name))  # TODO: raise a dedicated exception
        elif element_type == DicomElementType.REQUIRED:
            ds.__setattr__(field_name, '')
        elif element_type == DicomElementType.MANDATORY:
            raise Exception("missing field '{fieldName}'".format(fieldName = field_name))  # TODO: raise a dedicated exception

# # Dicom-Meta-Information-Header
#
# # Dicom-Data-Set
# # Used TransferSyntax: Little Endian Explicit
# (0008,0005) CS [ISO_IR 100]                             #  10, 1 SpecificCharacterSet
# (0008,0018) UI [1.2.276.0.7230010.3.1.4.34260742.2908.1486551644.225000] #  56, 1 SOPInstanceUID
# (0008,0050) SH [63]                                     #   2, 1 AccessionNumber
# (0008,0080) LO [REMOVED]              #  26, 1 InstitutionName
# (0008,0081) ST [REMOVED]         #  30, 1 InstitutionAddress
# (0010,0010) PN [SURNAME^NAME]                          #  14, 1 PatientName
# (0010,0020) LO [38]                                     #   2, 1 PatientID
# (0010,0030) DA [19710711]                               #   8, 1 PatientBirthDate
# (0010,0040) CS [F]                                      #   2, 1 PatientSex
# (0020,000d) UI [1.2.276.0.7230010.3.1.2.34260742.2908.1486551644.224998] #  56, 1 StudyInstanceUID
# (0020,000e) UI [1.2.276.0.7230010.3.1.3.34260742.2908.1486551644.224999] #  56, 1 SeriesInstanceUID
# (0032,1032) PN (no value available)                     #   0, 0 RequestingPhysician
# (0032,1060) LO [TC BACINO]                              #  10, 1 RequestedProcedureDescription
# (0038,0010) LO [30]                                     #   2, 1 AdmissionID
# (0040,0100) SQ (Sequence with explicit length #=1)      # 108, 1 ScheduledProcedureStepSequence
#   (fffe,e000) na (Item with explicit length #=8)          # 100, 1 Item
#     (0008,0060) CS [CT]                                     #   2, 1 Modality
#     (0040,0001) AE [CT99]                                   #   4, 1 ScheduledStationAETitle
#     (0040,0002) DA [20170208]                               #   8, 1 ScheduledProcedureStepStartDate
#     (0040,0003) TM [083000]                                 #   6, 1 ScheduledProcedureStepStartTime
#     (0040,0006) PN (no value available)                     #   0, 0 ScheduledPerformingPhysicianName
#     (0040,0007) LO [TC BACINO]                              #  10, 1 ScheduledProcedureStepDescription
#     (0040,0009) SH [134]                                    #   4, 1 ScheduledProcedureStepID
#     (0040,0010) SH [TC]                                     #   2, 1 ScheduledStationName
#   (fffe,e00d) na (ItemDelimitationItem for re-encoding)   #   0, 0 ItemDelimitationItem
# (fffe,e0dd) na (SequenceDelimitationItem for re-encod.) #   0, 0 SequenceDelimitationItem
# (0040,1001) SH [134]                                    #   4, 1 RequestedProcedureID
# (0040,1003) SH [LOW]                                    #   4, 1 RequestedProcedurePriority
