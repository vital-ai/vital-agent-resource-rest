from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional, Literal, Union

from vital_agent_resource_app.tools.github.common_models import GitHubRepoBase, GitHubOutputBase


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------

class GitHubActionsListWorkflowsInput(GitHubRepoBase):
    """List the workflows defined in a repository"""
    operation: Literal["list_workflows"] = Field(..., description="Operation to perform")
    max_results: Optional[int] = Field(30, description="Maximum workflows to return", ge=1, le=100)
    page: Optional[int] = Field(None, description="Page number for pagination", ge=1)

    model_config = {
        "json_schema_extra": {
            "example": {
                "operation": "list_workflows",
                "owner": "vital-ai",
                "repo": "vital-ai-sandbox"
            }
        }
    }


class GitHubActionsListRunsInput(GitHubRepoBase):
    """List workflow runs, optionally filtered"""
    operation: Literal["list_workflow_runs"] = Field(..., description="Operation to perform")
    workflow_id: Optional[str] = Field(
        None, description="Workflow numeric id or file name (e.g. 'ci.yml'); omit for all workflows"
    )
    branch: Optional[str] = Field(None, description="Filter by branch name")
    status: Optional[Literal[
        "queued", "in_progress", "completed", "success", "failure",
        "cancelled", "skipped", "timed_out", "action_required"
    ]] = Field(None, description="Filter by run status or conclusion")
    actor: Optional[str] = Field(None, description="Filter by the login that triggered the run")
    event: Optional[str] = Field(None, description="Filter by triggering event, e.g. 'push'")
    max_results: Optional[int] = Field(20, description="Maximum runs to return", ge=1, le=100)
    page: Optional[int] = Field(None, description="Page number for pagination", ge=1)


class GitHubActionsGetRunInput(GitHubRepoBase):
    """Get a single workflow run"""
    operation: Literal["get_workflow_run"] = Field(..., description="Operation to perform")
    run_id: int = Field(..., description="Workflow run id", ge=1)


class GitHubActionsListJobsInput(GitHubRepoBase):
    """List the jobs and step results for a workflow run"""
    operation: Literal["list_run_jobs"] = Field(..., description="Operation to perform")
    run_id: int = Field(..., description="Workflow run id", ge=1)
    filter: Optional[Literal["latest", "all"]] = Field("latest", description="Which attempt's jobs")
    max_results: Optional[int] = Field(30, description="Maximum jobs to return", ge=1, le=100)


class GitHubActionsTriggerInput(GitHubRepoBase):
    """Trigger a workflow_dispatch run.

    Gated behind allow_workflow_dispatch (default off) because it executes
    arbitrary CI. The workflow file must declare a workflow_dispatch trigger.
    """
    operation: Literal["trigger_workflow"] = Field(..., description="Operation to perform")
    workflow_id: str = Field(
        ..., description="Workflow numeric id or file name (e.g. 'ci.yml')", min_length=1
    )
    ref: str = Field(..., description="Branch or tag to run against", min_length=1)
    inputs: Optional[Dict[str, Any]] = Field(None, description="workflow_dispatch inputs")

    model_config = {
        "json_schema_extra": {
            "example": {
                "operation": "trigger_workflow",
                "owner": "vital-ai",
                "repo": "vital-ai-sandbox",
                "workflow_id": "ci.yml",
                "ref": "main",
                "inputs": {"environment": "staging"}
            }
        }
    }


class GitHubActionsCancelRunInput(GitHubRepoBase):
    """Cancel an in-flight workflow run"""
    operation: Literal["cancel_workflow_run"] = Field(..., description="Operation to perform")
    run_id: int = Field(..., description="Workflow run id", ge=1)


class GitHubActionsRerunInput(GitHubRepoBase):
    """Re-run a workflow run, or only its failed jobs.

    Shares the workflow-dispatch gate: a re-run executes CI just as a fresh
    dispatch does.
    """
    operation: Literal["rerun_workflow"] = Field(..., description="Operation to perform")
    run_id: int = Field(..., description="Workflow run id", ge=1)
    failed_jobs_only: Optional[bool] = Field(
        False, description="Re-run only the jobs that failed"
    )


class GitHubActionsRunLogsInput(GitHubRepoBase):
    """Fetch log text for a workflow run.

    GitHub returns logs as a zip archive; the tool unpacks it and returns the
    tail of each job's log, since raw CI logs run to megabytes.
    """
    operation: Literal["get_run_logs"] = Field(..., description="Operation to perform")
    run_id: int = Field(..., description="Workflow run id", ge=1)
    max_lines_per_file: Optional[int] = Field(
        50, description="Tail lines kept per log file", ge=1, le=500
    )
    max_files: Optional[int] = Field(10, description="Maximum log files to include", ge=1, le=50)


GitHubActionsToolInput = Union[
    GitHubActionsListWorkflowsInput,
    GitHubActionsListRunsInput,
    GitHubActionsGetRunInput,
    GitHubActionsListJobsInput,
    GitHubActionsTriggerInput,
    GitHubActionsCancelRunInput,
    GitHubActionsRerunInput,
    GitHubActionsRunLogsInput,
]

GITHUB_ACTIONS_OPERATION_MODELS = {
    "list_workflows": GitHubActionsListWorkflowsInput,
    "list_workflow_runs": GitHubActionsListRunsInput,
    "get_workflow_run": GitHubActionsGetRunInput,
    "list_run_jobs": GitHubActionsListJobsInput,
    "trigger_workflow": GitHubActionsTriggerInput,
    "cancel_workflow_run": GitHubActionsCancelRunInput,
    "rerun_workflow": GitHubActionsRerunInput,
    "get_run_logs": GitHubActionsRunLogsInput,
}


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------

class GitHubWorkflow(BaseModel):
    id: int = Field(..., description="Workflow id")
    name: str = Field(..., description="Workflow name")
    path: Optional[str] = Field(None, description="Path of the workflow file")
    state: Optional[str] = Field(None, description="active, disabled_manually, ...")
    html_url: Optional[str] = Field(None, description="Browser URL")
    created_at: Optional[str] = Field(None, description="Creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")


class GitHubWorkflowRun(BaseModel):
    id: int = Field(..., description="Run id")
    name: Optional[str] = Field(None, description="Workflow name")
    run_number: Optional[int] = Field(None, description="Run number within the workflow")
    status: Optional[str] = Field(None, description="queued, in_progress, completed")
    conclusion: Optional[str] = Field(None, description="success, failure, cancelled, ...")
    event: Optional[str] = Field(None, description="Triggering event")
    branch: Optional[str] = Field(None, description="Branch the run targeted")
    head_sha: Optional[str] = Field(None, description="Commit the run built")
    actor: Optional[str] = Field(None, description="Login that triggered the run")
    html_url: Optional[str] = Field(None, description="Browser URL")
    run_attempt: Optional[int] = Field(None, description="Attempt number")
    created_at: Optional[str] = Field(None, description="Creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")


class GitHubWorkflowStep(BaseModel):
    name: str = Field(..., description="Step name")
    status: Optional[str] = Field(None, description="Step status")
    conclusion: Optional[str] = Field(None, description="Step conclusion")
    number: Optional[int] = Field(None, description="Step number")


class GitHubWorkflowJob(BaseModel):
    id: int = Field(..., description="Job id")
    name: str = Field(..., description="Job name")
    status: Optional[str] = Field(None, description="Job status")
    conclusion: Optional[str] = Field(None, description="Job conclusion")
    html_url: Optional[str] = Field(None, description="Browser URL")
    started_at: Optional[str] = Field(None, description="Start timestamp")
    completed_at: Optional[str] = Field(None, description="Completion timestamp")
    steps: List[GitHubWorkflowStep] = Field(default_factory=list, description="Step results")


class GitHubRunLog(BaseModel):
    filename: str = Field(..., description="Path of the log file inside the archive")
    lines: List[str] = Field(default_factory=list, description="Tail of the log file")
    truncated: bool = Field(False, description="True if earlier lines were dropped")


class GitHubActionsToolOutput(GitHubOutputBase):
    """Output model for the GitHub actions tool"""
    tool: Literal["github_actions_tool"] = Field("github_actions_tool", description="Tool identifier")
    operation: str = Field(..., description="Operation that was performed")
    workflows: List[GitHubWorkflow] = Field(default_factory=list, description="Workflow definitions")
    runs: List[GitHubWorkflowRun] = Field(default_factory=list, description="Workflow runs")
    run: Optional[GitHubWorkflowRun] = Field(None, description="Single workflow run")
    jobs: List[GitHubWorkflowJob] = Field(default_factory=list, description="Jobs in a run")
    logs: List[GitHubRunLog] = Field(default_factory=list, description="Truncated log files")
    triggered: Optional[bool] = Field(None, description="True if a dispatch was accepted")
    dispatch_note: Optional[str] = Field(
        None,
        description="Explains that workflow_dispatch returns no run id, and how the run was located"
    )
    total_count: Optional[int] = Field(
        None,
        description="Corpus total reported by GitHub for the query, which may exceed "
                    "returned_count when results are paginated. Use returned_count for "
                    "what this response contains."
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "tool": "github_actions_tool",
                "operation": "list_workflow_runs",
                "repository": "vital-ai/vital-ai-sandbox",
                "runs": [
                    {
                        "id": 123456789,
                        "name": "CI",
                        "status": "completed",
                        "conclusion": "success",
                        "event": "push",
                        "branch": "main"
                    }
                ]
            }
        }
    }
