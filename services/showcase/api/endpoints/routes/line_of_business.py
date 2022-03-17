import logging
from typing import List, Dict
from uuid import UUID
from pydantic import BaseModel

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from api.db.models.related import (
    LobReadWithSandbox,
    OutOfBandReadPopulated,
)
from api.db.repositories.job_applicant import ApplicantRepository
from api.db.repositories.out_of_band import OutOfBandRepository
from api.endpoints.dependencies.db import get_db
from api.db.repositories.line_of_business import LobRepository
from api.db.repositories.student import StudentRepository

from api.services import sandbox, traction

router = APIRouter()
logger = logging.getLogger(__name__)


class CredentialsRead(BaseModel):
    attrs: Dict
    cred_def_id: str
    schema_id: str


class Credential(BaseModel):
    cred_type: str
    cred_protocol: str
    cred_def_id: str
    credential: str
    issue_state: str
    issue_role: str
    created_at: str
    updated_at: str
    id: str


class Workflow(BaseModel):
    workflow_state: str


class CredentialOfferRead(BaseModel):
    credential: Credential
    workflow: Workflow | None


@router.get(
    "/lobs",
    status_code=status.HTTP_200_OK,
    response_model=List[LobReadWithSandbox],
)
async def get_line_of_businesses(
    sandbox_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> List[LobReadWithSandbox]:
    # this should take some query params, sorting and paging params...
    repo = LobRepository(db_session=db)
    items = await repo.get_in_sandbox(sandbox_id)
    return items


@router.get(
    "/lobs/{lob_id}",
    status_code=status.HTTP_200_OK,
    response_model=LobReadWithSandbox,
)
async def get_line_of_business(
    sandbox_id: UUID,
    lob_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> LobReadWithSandbox:
    repo = LobRepository(db_session=db)
    item = await repo.get_by_id_with_sandbox(sandbox_id, lob_id)
    return item


@router.get(
    "/lobs/{lob_id}/out-of-band-msgs",
    status_code=status.HTTP_200_OK,
    response_model=List[OutOfBandReadPopulated],
)
async def get_out_of_band_messages(
    sandbox_id: UUID,
    lob_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> OutOfBandReadPopulated:
    # make sure lob is in this sandbox...
    lob_repo = LobRepository(db_session=db)
    lob = await lob_repo.get_by_id_with_sandbox(sandbox_id, lob_id)
    # go get all oob messages for the lob (recipient or sender)
    oob_repo = OutOfBandRepository(db_session=db)
    items = await oob_repo.get_for_lob(lob_id=lob.id)
    return items


@router.get(
    "/lobs/{lob_id}/credential-offer",
    status_code=status.HTTP_200_OK,
    response_model=List[CredentialOfferRead],
)
async def get_credential_offer(
    sandbox_id: UUID,
    lob_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> CredentialOfferRead:
    # make sure lob is in this sandbox...
    lob_repo = LobRepository(db_session=db)
    lob = await lob_repo.get_by_id_with_sandbox(sandbox_id, lob_id)
    # go get all creds the lob holds
    creds = await traction.tenant_get_credential_offers(lob.wallet_id, lob.wallet_key)
    return creds


@router.post(
    "/lobs/{lob_id}/credential-offer/{cred_issue_id}/accept",
    status_code=status.HTTP_200_OK,
)
async def accept_credential_offer(
    sandbox_id: UUID,
    lob_id: UUID,
    cred_issue_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    # make sure lob is in this sandbox...
    lob_repo = LobRepository(db_session=db)
    lob = await lob_repo.get_by_id_with_sandbox(sandbox_id, lob_id)
    # go get all creds the lob holds
    creds = await traction.tenant_accept_credential_offer(
        lob.wallet_id, lob.wallet_key, cred_issue_id
    )
    return creds


@router.post(
    "/lobs/{lob_id}/credential-offer/{cred_issue_id}/reject",
    status_code=status.HTTP_200_OK,
)
async def reject_credential_offer(
    sandbox_id: UUID,
    lob_id: UUID,
    cred_issue_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    # make sure lob is in this sandbox...
    lob_repo = LobRepository(db_session=db)
    lob = await lob_repo.get_by_id_with_sandbox(sandbox_id, lob_id)
    # go get all creds the lob holds
    creds = await traction.tenant_reject_credential_offer(
        lob.wallet_id, lob.wallet_key, cred_issue_id
    )
    return creds


@router.get(
    "/lobs/{lob_id}/credentials",
    status_code=status.HTTP_200_OK,
    response_model=List[CredentialsRead],
)
async def get_credentials(
    sandbox_id: UUID,
    lob_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> CredentialsRead:
    # make sure lob is in this sandbox...
    lob_repo = LobRepository(db_session=db)
    lob = await lob_repo.get_by_id_with_sandbox(sandbox_id, lob_id)
    # go get all creds the lob holds
    creds = await traction.tenant_get_credentials(lob.wallet_id, lob.wallet_key)
    return creds


@router.post(
    "/lobs/{lob_id}/create-invitation/student",
    status_code=status.HTTP_200_OK,
    response_model=sandbox.InviteStudentResponse,
)
async def create_invitation_for_student(
    sandbox_id: UUID,
    lob_id: UUID,
    payload: sandbox.InviteStudentRequest,
    db: AsyncSession = Depends(get_db),
) -> sandbox.InviteStudentResponse:
    return await sandbox.create_invitation_for_student(
        sandbox_id=sandbox_id, lob_id=lob_id, payload=payload, db=db
    )


@router.post(
    "/lobs/{lob_id}/create-invitation/applicant",
    status_code=status.HTTP_200_OK,
    response_model=sandbox.InviteApplicantResponse,
)
async def create_invitation_for_applicant(
    sandbox_id: UUID,
    lob_id: UUID,
    payload: sandbox.InviteApplicantRequest,
    db: AsyncSession = Depends(get_db),
) -> sandbox.InviteStudentResponse:
    return await sandbox.create_invitation_for_applicant(
        sandbox_id=sandbox_id, lob_id=lob_id, payload=payload, db=db
    )


@router.post(
    "/lobs/{lob_id}/accept-invitation",
    status_code=status.HTTP_200_OK,
    response_model=sandbox.AcceptInvitationResponse,
)
async def accept_invitation(
    sandbox_id: UUID,
    lob_id: UUID,
    payload: sandbox.AcceptInvitationRequest,
    db: AsyncSession = Depends(get_db),
) -> sandbox.AcceptInvitationResponse:
    return await sandbox.accept_invitation(
        sandbox_id=sandbox_id, lob_id=lob_id, payload=payload, db=db
    )


@router.post(
    "/lobs/{lob_id}/make-issuer",
    status_code=status.HTTP_200_OK,
)
async def promote_to_issuer(
    sandbox_id: UUID,
    lob_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    return await sandbox.promote_lob_to_issuer(
        sandbox_id=sandbox_id, lob_id=lob_id, db=db
    )


@router.post(
    "/lobs/{lob_id}/students/{student_id}/issue-degree",
    status_code=status.HTTP_200_OK,
)
async def issue_degree(
    sandbox_id: UUID,
    lob_id: UUID,
    student_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    s_repo = StudentRepository(db_session=db)
    lob_repo = LobRepository(db_session=db)

    student = await s_repo.get_by_id_in_sandbox(sandbox_id, student_id)
    faber = await lob_repo.get_by_id_with_sandbox(sandbox_id, lob_id)

    attrs = [
        {"name": "student_id", "value": student.student_id},
        {"name": "name", "value": student.name},
        {"name": "date", "value": student.date.date().strftime("%d-%m-%Y")},
        {"name": "degree", "value": student.degree},
        {"name": "age", "value": student.age},
    ]

    resp = await traction.tenant_issue_credential(
        faber.wallet_id,
        faber.wallet_key,
        str(student.connection_id),
        alias="degree",
        cred_def_id=str(faber.cred_def_id),
        attributes=attrs,
    )

    return resp


@router.post(
    "/lobs/{lob_id}/applicants/{applicant_id}/request-degree",
    status_code=status.HTTP_200_OK,
)
async def request_degree(
    sandbox_id: UUID,
    lob_id: UUID,
    applicant_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    a_repo = ApplicantRepository(db_session=db)
    lob_repo = LobRepository(db_session=db)

    applicant = await a_repo.get_by_id_in_sandbox(sandbox_id, applicant_id)
    acme = await lob_repo.get_by_id_with_sandbox(sandbox_id, lob_id)
    # going to get faber, so we can use their cred def id
    faber = await lob_repo.get_by_name_with_sandbox(sandbox_id, "Faber")

    proof_req = {
        "requested_attributes": [
            {
                "name": "degree",
                "restrictions": [{"cred_def_id": faber.cred_def_id}],
            },
            {
                "name": "date",
                "restrictions": [{"cred_def_id": faber.cred_def_id}],
            },
        ],
        "requested_predicates": [
            {
                "name": "age",
                "p_type": ">",
                "p_value": 18,
                "restrictions": [{"cred_def_id": faber.cred_def_id}],
            }
        ],
    }

    resp = await traction.tenant_request_credential_presentation(
        acme.wallet_id,
        acme.wallet_key,
        str(applicant.connection_id),
        alias=applicant.alias,
        proof_req=proof_req,
    )

    return resp