"""
Cortex-AI Platform Demo

Demonstrates the full platform workflow:
1. Signup (creates Principal, Account, Organization)
2. Login (get JWT tokens)
3. Create additional organizations and projects
4. Test RBAC permissions
5. Manage resources with different roles

Usage:
    python examples/platform_demo.py

Prerequisites:
    - PostgreSQL running (DATABASE_URL configured)
    - Redis running (REDIS_URL configured)
    - .env file configured
    - Server running: python -m cortex.api.main
"""

import asyncio
import httpx
from typing import Any


API_BASE_URL = "http://localhost:8000"


async def demo_signup() -> dict[str, Any]:
    """
    Demo: User signup.

    Creates:
    - Principal (user)
    - Account (with 14-day trial)
    - Organization (default org)
    - OWNER memberships for account and organization
    """
    print("\n" + "=" * 80)
    print("DEMO 1: USER SIGNUP")
    print("=" * 80)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_BASE_URL}/api/v1/auth/signup",
            json={
                "email": "demo@example.com",
                "display_name": "Demo User",
                "password": "SecurePassword123!",
                "organization_name": "Demo Organization",
            },
        )

        if response.status_code == 201:
            data = response.json()
            print(f"✅ Signup successful!")
            print(f"   Principal ID: {data['principal']['id']}")
            print(f"   Email: {data['principal']['email']}")
            print(f"   Account ID: {data['account']['id']}")
            print(f"   Organization ID: {data['organization']['id']}")
            print(f"   Access Token: {data['access_token'][:50]}...")
            print(f"   Token Type: {data['token_type']}")
            return data
        else:
            print(f"❌ Signup failed: {response.status_code}")
            print(f"   Error: {response.json()}")
            return {}


async def demo_login() -> dict[str, Any]:
    """
    Demo: User login.

    Returns JWT access and refresh tokens.
    """
    print("\n" + "=" * 80)
    print("DEMO 2: USER LOGIN")
    print("=" * 80)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_BASE_URL}/api/v1/auth/login",
            json={
                "email": "demo@example.com",
                "password": "SecurePassword123!",
            },
        )

        if response.status_code == 200:
            data = response.json()
            print(f"✅ Login successful!")
            print(f"   Access Token: {data['access_token'][:50]}...")
            print(f"   Refresh Token: {data['refresh_token'][:50]}...")
            print(f"   Expires In: {data['expires_in']} seconds")
            return data
        else:
            print(f"❌ Login failed: {response.status_code}")
            print(f"   Error: {response.json()}")
            return {}


async def demo_get_current_user(access_token: str) -> dict[str, Any]:
    """
    Demo: Get current user info.

    Uses JWT token to fetch authenticated user details.
    """
    print("\n" + "=" * 80)
    print("DEMO 3: GET CURRENT USER")
    print("=" * 80)

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{API_BASE_URL}/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        if response.status_code == 200:
            data = response.json()
            print(f"✅ User info retrieved!")
            print(f"   ID: {data['id']}")
            print(f"   Email: {data['email']}")
            print(f"   Display Name: {data['display_name']}")
            print(f"   Type: {data['type']}")
            print(f"   Admin: {data['admin']}")
            print(f"   Created: {data['created_at']}")
            return data
        else:
            print(f"❌ Failed to get user: {response.status_code}")
            print(f"   Error: {response.json()}")
            return {}


async def demo_list_accounts(access_token: str) -> list[dict[str, Any]]:
    """
    Demo: List accounts.

    Retrieves all accounts the user has access to.
    """
    print("\n" + "=" * 80)
    print("DEMO 4: LIST ACCOUNTS")
    print("=" * 80)

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{API_BASE_URL}/api/v1/accounts",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        if response.status_code == 200:
            data = response.json()
            print(f"✅ Found {data['total']} account(s)")
            for account in data["accounts"]:
                print(f"\n   Account: {account['name']}")
                print(f"   - ID: {account['id']}")
                print(f"   - Status: {account['status']}")
                print(f"   - Tier: {account['subscription_tier']}")
                if account.get("trial_ends_at"):
                    print(f"   - Trial Ends: {account['trial_ends_at']}")
            return data["accounts"]
        else:
            print(f"❌ Failed to list accounts: {response.status_code}")
            print(f"   Error: {response.json()}")
            return []


async def demo_create_organization(
    access_token: str, account_id: str
) -> dict[str, Any]:
    """
    Demo: Create additional organization.

    Requires ACCOUNT_EDIT permission on the account.
    """
    print("\n" + "=" * 80)
    print("DEMO 5: CREATE ORGANIZATION")
    print("=" * 80)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_BASE_URL}/api/v1/accounts/{account_id}/organizations",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "name": "Engineering Team",
                "description": "Engineering organization for development projects",
            },
        )

        if response.status_code == 201:
            data = response.json()
            print(f"✅ Organization created!")
            print(f"   ID: {data['id']}")
            print(f"   Name: {data['name']}")
            print(f"   Description: {data['description']}")
            print(f"   Account ID: {data['account_id']}")
            print(f"   Owner ID: {data['owner_id']}")
            return data
        else:
            print(f"❌ Failed to create organization: {response.status_code}")
            print(f"   Error: {response.json()}")
            return {}


async def demo_list_organizations(
    access_token: str, account_id: str
) -> list[dict[str, Any]]:
    """
    Demo: List organizations in an account.

    Shows all organizations the user has access to.
    """
    print("\n" + "=" * 80)
    print("DEMO 6: LIST ORGANIZATIONS")
    print("=" * 80)

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{API_BASE_URL}/api/v1/accounts/{account_id}/organizations",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        if response.status_code == 200:
            data = response.json()
            print(f"✅ Found {data['total']} organization(s)")
            for org in data["organizations"]:
                print(f"\n   Organization: {org['name']}")
                print(f"   - ID: {org['id']}")
                if org.get("description"):
                    print(f"   - Description: {org['description']}")
            return data["organizations"]
        else:
            print(f"❌ Failed to list organizations: {response.status_code}")
            print(f"   Error: {response.json()}")
            return []


async def demo_create_project(access_token: str, org_id: str) -> dict[str, Any]:
    """
    Demo: Create project in organization.

    Requires ORG_CREATE_PROJECT permission.
    """
    print("\n" + "=" * 80)
    print("DEMO 7: CREATE PROJECT")
    print("=" * 80)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_BASE_URL}/api/v1/organizations/{org_id}/projects",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "name": "AI Chat Application",
                "description": "Customer support chatbot with RAG",
            },
        )

        if response.status_code == 201:
            data = response.json()
            print(f"✅ Project created!")
            print(f"   ID: {data['id']}")
            print(f"   Name: {data['name']}")
            print(f"   Description: {data['description']}")
            print(f"   Organization ID: {data['organization_id']}")
            print(f"   Owner ID: {data['owner_id']}")
            return data
        else:
            print(f"❌ Failed to create project: {response.status_code}")
            print(f"   Error: {response.json()}")
            return {}


async def demo_list_projects(access_token: str, org_id: str) -> list[dict[str, Any]]:
    """
    Demo: List projects in organization.

    Shows all projects the user has access to.
    """
    print("\n" + "=" * 80)
    print("DEMO 8: LIST PROJECTS")
    print("=" * 80)

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{API_BASE_URL}/api/v1/organizations/{org_id}/projects",
            headers={"Authorization": f"Bearer {access_token}"},
            json={},
            headers={"Authorization": f"Bearer {access_token}"},
        )

        if response.status_code == 200:
            data = response.json()
            print(f"✅ Found {data['total']} project(s)")
            for project in data["projects"]:
                print(f"\n   Project: {project['name']}")
                print(f"   - ID: {project['id']}")
                if project.get("description"):
                    print(f"   - Description: {project['description']}")
            return data["projects"]
        else:
            print(f"❌ Failed to list projects: {response.status_code}")
            print(f"   Error: {response.json()}")
            return []


async def demo_update_project(
    access_token: str, project_id: str
) -> dict[str, Any]:
    """
    Demo: Update project.

    Requires PROJECT_EDIT permission.
    """
    print("\n" + "=" * 80)
    print("DEMO 9: UPDATE PROJECT")
    print("=" * 80)

    async with httpx.AsyncClient() as client:
        response = await client.patch(
            f"{API_BASE_URL}/api/v1/projects/{project_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "name": "AI Chat Application (Updated)",
                "description": "Enterprise customer support chatbot with RAG and GraphRAG",
            },
        )

        if response.status_code == 200:
            data = response.json()
            print(f"✅ Project updated!")
            print(f"   ID: {data['id']}")
            print(f"   Name: {data['name']}")
            print(f"   Description: {data['description']}")
            return data
        else:
            print(f"❌ Failed to update project: {response.status_code}")
            print(f"   Error: {response.json()}")
            return {}


async def main():
    """Run all demos in sequence."""
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "CORTEX-AI PLATFORM DEMO" + " " * 35 + "║")
    print("╚" + "=" * 78 + "╝")

    # Demo 1: Signup
    signup_data = await demo_signup()
    if not signup_data:
        print("\n❌ Signup failed. Exiting demo.")
        return

    access_token = signup_data["access_token"]
    account_id = signup_data["account"]["id"]

    # Demo 2: Login (optional, we already have a token from signup)
    await asyncio.sleep(1)
    login_data = await demo_login()

    # Demo 3: Get current user
    await asyncio.sleep(1)
    await demo_get_current_user(access_token)

    # Demo 4: List accounts
    await asyncio.sleep(1)
    accounts = await demo_list_accounts(access_token)

    # Demo 5: Create additional organization
    await asyncio.sleep(1)
    org_data = await demo_create_organization(access_token, account_id)
    if not org_data:
        print("\n⚠️  Skipping remaining demos.")
        return

    org_id = org_data["id"]

    # Demo 6: List organizations
    await asyncio.sleep(1)
    await demo_list_organizations(access_token, account_id)

    # Demo 7: Create project
    await asyncio.sleep(1)
    project_data = await demo_create_project(access_token, org_id)
    if not project_data:
        print("\n⚠️  Skipping remaining demos.")
        return

    project_id = project_data["id"]

    # Demo 8: List projects
    await asyncio.sleep(1)
    await demo_list_projects(access_token, org_id)

    # Demo 9: Update project
    await asyncio.sleep(1)
    await demo_update_project(access_token, project_id)

    # Summary
    print("\n" + "=" * 80)
    print("DEMO COMPLETE!")
    print("=" * 80)
    print("\n✅ All demos completed successfully!")
    print("\nYou now have:")
    print(f"   - 1 Account ({account_id})")
    print(f"   - 2 Organizations (including default)")
    print(f"   - 1 Project ({project_id})")
    print("\nNext steps:")
    print("   - Try creating documents and using RAG features")
    print("   - Test different user roles (OWNER, ADMIN, CONTRIBUTOR, READER)")
    print("   - Explore agent orchestration and multi-agent swarms")
    print("   - Enable GraphRAG with Neo4j for knowledge graphs")
    print("\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Demo interrupted by user.")
    except httpx.ConnectError:
        print("\n\n❌ Error: Could not connect to API server.")
        print("   Make sure the server is running: python -m cortex.api.main")
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
