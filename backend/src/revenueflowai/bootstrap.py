"""First-tenant bootstrap: creates an organization, a business unit, and an
admin application user, so a new deployment doesn't need manual SQL before
the first admin can sign in. Idempotent: re-running with the same arguments
changes nothing.

    python -m revenueflowai.bootstrap --org-name "Acme" --org-slug acme \
        --bu-code BU1 --bu-name "Business Unit 1" \
        --admin-subject <keycloak sub> --admin-email admin@acme.test --admin-name "Admin"
"""

import asyncio

import typer
from sqlalchemy import select

from revenueflowai.auth.deps import pending_subject_for
from revenueflowai.db import AsyncSessionLocal
from revenueflowai.models.tenancy import AppUser, BusinessUnit, Organization

app = typer.Typer(add_completion=False)


async def _bootstrap(
    org_name: str, org_slug: str, bu_code: str, bu_name: str,
    admin_subject: str, admin_email: str, admin_name: str,
) -> None:
    async with AsyncSessionLocal() as session:
        org = (await session.execute(
            select(Organization).where(Organization.slug == org_slug)
        )).scalar_one_or_none()
        if org is None:
            org = Organization(name=org_name, slug=org_slug)
            session.add(org)
            await session.flush()

        bu = (await session.execute(
            select(BusinessUnit).where(
                BusinessUnit.organization_id == org.id, BusinessUnit.code == bu_code
            )
        )).scalar_one_or_none()
        if bu is None:
            bu = BusinessUnit(organization_id=org.id, code=bu_code, name=bu_name)
            session.add(bu)
            await session.flush()

        user = (await session.execute(
            select(AppUser).where(AppUser.oidc_subject == admin_subject)
        )).scalar_one_or_none()
        if user is None:
            session.add(AppUser(
                oidc_subject=admin_subject, email=admin_email, display_name=admin_name,
                role="admin", organization_id=org.id,
            ))

        await session.commit()
        typer.echo(
            f"Bootstrapped organization '{org.slug}', business unit '{bu.code}', admin '{admin_email}'."
        )


@app.command()
def bootstrap(
    org_name: str = typer.Option(...),
    org_slug: str = typer.Option(...),
    bu_code: str = typer.Option("BU1"),
    bu_name: str = typer.Option("Business Unit 1"),
    admin_subject: str | None = typer.Option(
        None, help="Keycloak 'sub' of the first admin. Omit to bind on first verified sign-in."
    ),
    admin_email: str = typer.Option(...),
    admin_name: str = typer.Option("Administrator"),
) -> None:
    subject = admin_subject or pending_subject_for(admin_email)
    asyncio.run(_bootstrap(org_name, org_slug, bu_code, bu_name, subject, admin_email, admin_name))


if __name__ == "__main__":
    app()
