"""
PSK set management API endpoints.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import PskManager
from ..services.audit_log import audit_log
from ..middleware.auth import require_auth
from ..services.session_manager import Session as AuthSession

logger = logging.getLogger(__name__)


class PskSetRequest(BaseModel):
    """Request model for creating/updating PSK sets"""
    id: str = Field(description="Logical PSK set ID (stable identifier)")
    name: str = Field(description="Human-friendly name")
    ssid: str = Field(description="SSID these PSKs are valid for")
    description: str = Field(default="", description="Optional description")
    psks: List[str] = Field(default_factory=list, description="List of PSK strings")


class PskSetResponse(BaseModel):
    """Response model for PSK sets"""
    id: str
    name: str
    ssid: str
    description: str
    psks: List[str]


class PskSetSummary(BaseModel):
    """Summary response model for PSK sets (without passphrases)"""
    id: str
    name: str
    ssid: str
    description: str
    psk_count: int


router = APIRouter(prefix="/api/psk_sets", tags=["PSK Sets"])


def _to_response(psk_set) -> PskSetResponse:
    return PskSetResponse(
        id=psk_set.id,
        name=psk_set.name,
        ssid=psk_set.ssid,
        description=psk_set.description or "",
        psks=psk_set.psks,
    )


def _to_summary(psk_set) -> PskSetSummary:
    """Convert PSK set to summary (without passphrases for security)"""
    return PskSetSummary(
        id=psk_set.id,
        name=psk_set.name,
        ssid=psk_set.ssid,
        description=psk_set.description or "",
        psk_count=len(psk_set.psks),
    )


@router.post("", response_model=PskSetResponse)
async def create_psk_set(
    body: PskSetRequest,
    request: Request,
    db: Session = Depends(get_db),
    session: AuthSession = Depends(require_auth)
) -> PskSetResponse:
    """Create a new PSK set."""
    try:
        psk_manager: PskManager = request.app.state.psk_manager
        created = psk_manager.create_psk_set(
            db=db,
            psk_set_id=body.id,
            name=body.name,
            ssid=body.ssid,
            description=body.description,
            psks=body.psks,
        )

        # Audit log PSK set creation
        audit_log.log_psk_set_create(body.id, body.name, len(body.psks), success=True)

        return _to_response(created)
    except ValueError as e:
        audit_log.log_psk_set_create(body.id, body.name, len(body.psks), success=False, error=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating PSK set: {e}")
        audit_log.log_psk_set_create(body.id, body.name, len(body.psks), success=False, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to create PSK set: {str(e)}")


@router.get("", response_model=List[PskSetSummary])
async def list_psk_sets(
    request: Request,
    db: Session = Depends(get_db),
) -> List[PskSetSummary]:
    """List all PSK sets (passphrases redacted for security)."""
    try:
        psk_manager: PskManager = request.app.state.psk_manager
        sets = psk_manager.list_psk_sets(db)
        return [_to_summary(s) for s in sets]
    except Exception as e:
        logger.error(f"Error listing PSK sets: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list PSK sets: {str(e)}")


@router.get("/{psk_set_id}", response_model=PskSetResponse)
async def get_psk_set(
    psk_set_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> PskSetResponse:
    """Get a specific PSK set."""
    try:
        psk_manager: PskManager = request.app.state.psk_manager
        psk_set = psk_manager.get_psk_set(db, psk_set_id)
        if not psk_set:
            raise HTTPException(status_code=404, detail=f"PSK set {psk_set_id} not found")
        return _to_response(psk_set)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting PSK set {psk_set_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get PSK set: {str(e)}")


@router.put("/{psk_set_id}", response_model=PskSetResponse)
async def update_psk_set(
    psk_set_id: str,
    body: PskSetRequest,
    request: Request,
    db: Session = Depends(get_db),
    session: AuthSession = Depends(require_auth)
) -> PskSetResponse:
    """Update an existing PSK set."""
    try:
        psk_manager: PskManager = request.app.state.psk_manager
        updated = psk_manager.update_psk_set(
            db=db,
            psk_set_id=psk_set_id,
            name=body.name,
            description=body.description,
            psks=body.psks,
        )
        if not updated:
            audit_log.log_psk_set_update(psk_set_id, len(body.psks), success=False, error="PSK set not found")
            raise HTTPException(status_code=404, detail=f"PSK set {psk_set_id} not found")

        # Audit log PSK set update
        audit_log.log_psk_set_update(psk_set_id, len(body.psks), success=True)

        return _to_response(updated)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating PSK set {psk_set_id}: {e}")
        audit_log.log_psk_set_update(psk_set_id, len(body.psks), success=False, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to update PSK set: {str(e)}")


@router.delete("/{psk_set_id}")
async def delete_psk_set(
    psk_set_id: str,
    request: Request,
    db: Session = Depends(get_db),
    session: AuthSession = Depends(require_auth)
):
    """Delete a PSK set."""
    try:
        psk_manager: PskManager = request.app.state.psk_manager
        success = psk_manager.delete_psk_set(db, psk_set_id)
        if not success:
            audit_log.log_psk_set_delete(psk_set_id, success=False, error="PSK set not found")
            raise HTTPException(status_code=404, detail=f"PSK set {psk_set_id} not found")

        # Audit log PSK set deletion
        audit_log.log_psk_set_delete(psk_set_id, success=True)

        return {"success": True, "message": f"PSK set {psk_set_id} deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting PSK set {psk_set_id}: {e}")
        audit_log.log_psk_set_delete(psk_set_id, success=False, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to delete PSK set: {str(e)}")


@router.post("/import_csv", response_model=PskSetResponse)
async def import_psk_set_from_csv(
    request: Request,
    db: Session = Depends(get_db),
    session: AuthSession = Depends(require_auth),
    file: UploadFile = File(...),
    id: str = Form(..., description="Logical PSK set ID"),
    name: str = Form(..., description="Human-friendly name"),
    ssid: str = Form(..., description="SSID these PSKs are valid for"),
    description: str = Form("", description="Optional description"),
) -> PskSetResponse:
    """
    Import a PSK set from a CSV file exported by the DPSK tool.

    Expects a header with a 'Passphrase' column and will ignore comment
    lines starting with '#'.
    """
    try:
        psk_manager: PskManager = request.app.state.psk_manager

        content = await file.read()
        raw_lines = content.decode("utf-8", errors="ignore").splitlines()

        # Normalize lines, skip leading comments and noise until we find a header
        import csv

        cleaned_lines = []
        header_found = False
        for line in raw_lines:
            # Strip UTF-8 BOM and whitespace
            stripped = line.lstrip("\ufeff").rstrip("\n\r")
            if not stripped.strip():
                continue
            if not header_found:
                # Skip comment/metadata lines
                if stripped.lstrip().startswith("#"):
                    continue
                # Treat first non-comment line as header
                header_found = True
                cleaned_lines.append(stripped)
            else:
                cleaned_lines.append(stripped)

        if not cleaned_lines:
            raise HTTPException(
                status_code=400,
                detail="CSV appears to be empty or only comments.",
            )

        reader = csv.DictReader(cleaned_lines)

        # Find the actual Passphrase column (handle stray spaces/quotes)
        fieldnames = reader.fieldnames or []
        pass_col = None
        for name in fieldnames:
            normalized = name.strip().strip('"').lower()
            if normalized == "passphrase":
                pass_col = name
                break

        if not pass_col:
            raise HTTPException(
                status_code=400,
                detail=f"No 'Passphrase' column found in CSV header (got: {fieldnames}).",
            )

        psks = []
        for row in reader:
            raw = row.get(pass_col)
            if raw:
                psks.append(str(raw).strip())

        if not psks:
            raise HTTPException(
                status_code=400,
                detail="No PSK values found in CSV rows.",
            )

        # If a PSK set with this ID already exists, update it instead of failing.
        existing = psk_manager.get_psk_set(db, id)
        if existing:
            updated = psk_manager.update_psk_set(
                db=db,
                psk_set_id=id,
                name=name or existing.name,
                description=description or existing.description,
                psks=psks,
            )
            logger.info("Updated existing PSK set %s via CSV import", id)
            return _to_response(updated)

        created = psk_manager.create_psk_set(
            db=db,
            psk_set_id=id,
            name=name,
            ssid=ssid,
            description=description or f"Imported from {file.filename}",
            psks=psks,
        )

        return _to_response(created)

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error importing PSK set from CSV: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to import PSK set: {str(e)}")

