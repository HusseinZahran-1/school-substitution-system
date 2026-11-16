"""Keep existing administrator accounts usable after licensing is introduced."""
from datetime import datetime, timezone
import hashlib
import secrets

from alembic import op
import sqlalchemy as sa

revision = "0005_legacy_licenses"
down_revision = "0004_accounts_and_licenses"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    accounts = sa.table("admin_accounts", sa.column("id", sa.Integer()))
    licenses = sa.table(
        "license_keys",
        sa.column("id", sa.Integer()),
        sa.column("key_hash", sa.String(64)),
        sa.column("status", sa.String(20)),
        sa.column("assigned_user_id", sa.Integer()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("activated_at", sa.DateTime(timezone=True)),
    )
    now = datetime.now(timezone.utc)
    for user_id in connection.execute(sa.select(accounts.c.id)).scalars():
        already_licensed = connection.execute(
            sa.select(licenses.c.id).where(licenses.c.assigned_user_id == user_id)
        ).first()
        if already_licensed:
            continue
        # The random pre-hash is discarded. This compatibility license preserves
        # the already-authorized account without exposing or inventing a key.
        key_hash = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
        connection.execute(licenses.insert().values(
            key_hash=key_hash,
            status="ACTIVATED",
            assigned_user_id=user_id,
            created_at=now,
            activated_at=now,
        ))


def downgrade():
    # Existing accounts stay licensed; deleting their compatibility licenses
    # would unexpectedly revoke access during a downgrade.
    pass
