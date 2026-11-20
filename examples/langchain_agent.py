"""GroundTruth Protocol: LangChain / LangGraph Agent Integration Example.

Exposes physical ground truth verification as a native LangChain StructuredTool.
"""
import os
from typing import List, Optional
import requests
from pydantic import BaseModel, Field

BASE_URL = os.getenv("GROUNDTRUTH_BASE_URL", "http://127.0.0.1:8000")

class StorefrontAuditInput(BaseModel):
    business_name: str = Field(description="Name of the commercial business")
    address: str = Field(description="Street address in the Portland, OR metropolitan area")
    questions: List[str] = Field(description="List of specific physical facts to verify on-site")

def verify_portland_storefront(business_name: str, address: str, questions: List[str]) -> str:
    """
    Calls GroundTruth Protocol Node #001 to dispatch a human field inspector
    in Portland, OR when online data is stale, ambiguous, or missing.
    """
    payload = {
        "business_name": business_name,
        "address": address,
        "specific_questions": questions,
        "stated_purpose": "LangChain autonomous agent verification",
        "client_id": "langchain_agent"
    }

    resp = requests.post(f"{BASE_URL}/v1/dispatch/storefront", json=payload)
    if resp.status_code == 200:
        data = resp.json()
        return (
            f"Physical dispatch initiated (Task ID: {data['task_id']}). "
            f"Status is {data['status']}. Operator in Portland has received the task card."
        )
    elif resp.status_code == 429:
        return f"Policy limit: {resp.json().get('detail')}"
    else:
        return f"Failed to dispatch: {resp.text}"

# LangChain Tool definition:
# from langchain.tools import StructuredTool
# ground_truth_tool = StructuredTool.from_function(
#     func=verify_portland_storefront,
#     name="portland_physical_verification",
#     description="Use this tool when digital records regarding a commercial property in Portland, OR are conflicting or unverified.",
#     args_schema=StorefrontAuditInput
# )

if __name__ == "__main__":
    print("Testing LangChain tool function directly...")
    result = verify_portland_storefront(
        business_name="Powell's Books",
        address="1005 W Burnside St, Portland, OR",
        questions=["Is the main entrance open?"]
    )
    print("Result:", result)
