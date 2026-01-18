# Workflow Requirements: Publish Social Media Post using Social Media Planning Tool

## Purpose & Scope

**Purpose:** Publish social media posts from the Social-Media-Posts database through the social media planning tool (Metricool) to designated platforms, ensuring all required validation, media processing, and scheduling steps are completed.

**Scope:** 
- **Source Database:** Social-Media-Posts (`224e7361-6c27-806a-be41-dfcf338c0624`)
- **Target System:** Metricool API (social media planning tool)
- **Platforms:** Instagram, Facebook, Twitter/X, LinkedIn, TikTok, YouTube, Threads, Google Business Profile, Pinterest, Twitch
- **Trigger:** Manual or scheduled execution when posts are ready for publication
- **Frequency:** On-demand or scheduled (varies by project/client needs)

## Canonical Relationships

**Data Flow:**
```
Social-Media-Posts → User-Workflow → Agent-Workflow → Agent-Functions → Tasks → Metricool API
```

**Entity Relationships:**
- **Posts ↔ Workflows:** Social-Media-Posts have a relation to User-Workflows (via Projects or direct relation)
- **Workflows ↔ Functions:** User-Workflows link to Agent-Workflows, which link to Agent-Functions
- **Functions ↔ Tasks:** Agent-Functions create and execute Tasks (Agent-Tasks database)
- **Tasks ↔ Metricool:** Tasks execute Metricool API calls and update Social-Media-Posts with results

**Metricool Artifacts:**
- Metricool Post ID (returned after scheduling/publish)
- Metricool Brand ID (required for API calls)
- Metricool User ID & User Token (authentication)
- Metricool Media IDs (returned after media upload)
- Metricool Response Data (raw API response)
- Metricool Sync Log (human-readable sync notes)
- Autolist ID (for posts added to Metricool Autolists)

## Data & Schema Assumptions

### Required Fields (Social-Media-Posts Database)

**Critical Fields (must be populated before publishing):**
- **Name** (title): Post title/identifier
- **Caption**: Final candidate caption (must be under platform character limits)
- **Platform(s)**: At least one platform must be selected (multi-select: instagram, facebook, twitter, linkedin, tiktok, youtube, etc.)
- **Status**: Must be "READY TO POST" or "DRAFT" (status property)
- **Scheduled Publish Date/Time**: Target publish timestamp (date property)
- **Timezone** or **Publication Date Timezone**: Timezone for scheduling (select/text property)

**Required for Metricool Integration:**
- **Metricool Brand ID**: Brand/blog ID required for Metricool API calls
- **Metricool User ID**: User ID for Metricool API authentication
- **Metricool User Token**: X-Mc-Auth token (stored securely, referenced in post)

**Validation Fields:**
- **Validation Status**: Must pass "Validated" before API call (select: Pending, Validated, Invalid, Error)
- **Pre-flight Checks**: Validation results before any API calls
- **Media Processing Status**: Must be "Uploaded" if media is required (select: Pending, Processing, Normalized, Failed, Uploaded)

### Acceptable States

**Post Status Lifecycle:**
- `Not started` → `DRAFT` → `READY TO POST` → `Done` (after successful publish)

**Sync Status Lifecycle:**
- `READY_FOR_SYNC` → `VALIDATING` → `MEDIA_PROCESSING` (if media required) → `API_CALL_PENDING` → `METRICOOL_SCHEDULED` → `METRICOOL_PUBLISHED` OR `METRICOOL_FAILED` (with error details)

**Validation Status:**
- `Pending` → `Validated` (pass) OR `Invalid` (fail with details) OR `Error` (validation error)

**Media Processing Status (if media required):**
- `Pending` → `Processing` → `Normalized` → `Uploaded` OR `Failed` (with error in Media Processing Log)

### Relation Integrity Requirements

**Required Relations:**
- **Clients**: Post must be linked to at least one Client (for billing/tracking)
- **Projects**: Post should be linked to a Project (for grouping analytics)

**Optional Relations:**
- **Photos**: One or more photos referenced in post draft
- **Videos**: Videos from Video Library referenced in post
- **Blog Post Drafts**: Related blog post used as source context
- **Documents**: Related documents
- **Topics**: Topical tags for content grouping
- **Marketing Channels**: Marketing channel classification
- **Tasks**: Operational tasks related to preparing/scheduling/fixing post

**Relation Validation:**
- Photos relation must contain valid photo records if media type requires photos
- Videos relation must contain valid video records if media type requires videos
- All relations must point to existing, non-archived records

## Agent Roles & Responsibilities

### Manual Decision-Making (User/Human Agent)
- **Post Selection**: User selects which draft post(s) to publish
- **Caption Editing**: User reviews and edits AI-generated captions (Caption Draft 1-AI through Caption Draft 5-AI) and finalizes Caption field
- **Platform Selection**: User selects target platform(s) based on content type and audience
- **Scheduling Decision**: User sets Scheduled Publish Date/Time and timezone
- **Media Approval**: User approves media assets before upload
- **Publication Approval**: User approves final post before API call
- **Error Resolution**: User reviews and resolves errors (Last Error Details, Metricool Sync Log)

### Automated Validation (Agent-Workflow Functions)
- **Required Fields Validation**: Check that all critical fields are populated
- **Platform-Specific Validation**: 
  - Validate caption length against platform limits
  - Validate media requirements (photos vs. videos) match platform capabilities
  - Validate scheduling constraints (minimum scheduling time in future, timezone handling)
- **Relation Integrity Validation**: Ensure all required relations are valid and non-archived
- **Media Readiness Validation**: Check Media Processing Status is "Uploaded" if media is required
- **Metricool Token Validation**: Verify Metricool User Token and User ID are valid
- **Pre-flight Checks**: Execute all validation rules and populate Pre-flight Checks field

### Automated Execution (Agent-Workflow Functions)
- **Media Normalization & Upload**: Normalize media files, upload to Metricool, retrieve Metricool Media IDs
- **Metricool Payload Preparation**: Build Metricool API request payload with:
  - Post content (Caption, First Comment if provided)
  - Media IDs (Metricool Media IDs)
  - Platform(s)
  - Scheduled Publish Date/Time with timezone
  - Brand ID, User ID, Authentication token
  - Location (if provided)
  - Campaign (if provided)
- **API Call Execution**: Call Metricool API to schedule/publish post
- **Response Processing**: Parse Metricool API response, extract Metricool Post ID, update Sync Status
- **State Updates**: Update Status, Post Status, Sync Status, Last Sync Time based on API response
- **Error Handling**: Capture errors in Last Error Details, set Sync Status to METRICOOL_FAILED, increment Retry Count if applicable

### Automated Logging & Evidence (Agent-Workflow Functions)
- **Execution Logging**: Log all operations to Metricool Sync Log (human-readable notes)
- **API Call History**: Record all outbound API calls with timestamps, request/response details
- **State Change Logging**: Log all status changes with timestamps
- **Evidence Bundle**: Attach/link:
  - Pre-flight validation evidence (Pre-flight Checks field)
  - Metricool API request/response (Metricool Response Data field)
  - Media upload evidence (Metricool Media IDs field)
  - Post-state evidence (Status, Post Status, Sync Status fields at completion)
- **Change Log**: Record all field modifications with before/after values and timestamps

## Step-by-Step Workflow Structure

### Step 1: Intake & Selection of Draft Post(s)
**Agent Role:** User (Manual)  
**Description:** User selects one or more draft posts from Social-Media-Posts database that are ready for publication.  
**Inputs:** Social-Media-Posts database query filtered by Status="READY TO POST" or Status="DRAFT"  
**Validation:** Post must exist, must not be archived, must have Status in acceptable range  
**Outputs:** Selected post page ID(s)  
**Agent-Function:** `select_draft_posts_for_publication(post_ids: List[str]) -> List[str]`

### Step 2: Required Fields & Media Readiness Validation
**Agent Role:** Agent-Workflow (Automated)  
**Description:** Validate that all required fields are populated, relations are intact, and media is ready if required.  
**Inputs:** Post page ID, Social-Media-Posts database schema  
**Validation:**
- Required fields: Name, Caption, Platform(s), Scheduled Publish Date/Time, Timezone, Metricool Brand ID, Metricool User ID, Metricool User Token
- Caption length vs. platform character limits
- Media Processing Status = "Uploaded" if Photos or Videos relations are populated
- All relations point to valid, non-archived records
- Validation Status set to "Validated" if all checks pass  
**Outputs:** Validation Status, Pre-flight Checks field populated with validation results  
**Agent-Function:** `validate_post_requirements(post_id: str) -> Dict[str, Any]`

### Step 3: Platform Rules Review
**Agent Role:** Agent-Workflow (Automated)  
**Description:** Review platform-specific rules and constraints (caption length, media types, scheduling windows).  
**Inputs:** Post page ID, Platform(s) selection, Caption, Media types  
**Validation:**
- Platform-specific caption length limits (Instagram: 2200, Twitter: 280, etc.)
- Media type compatibility (photos for Instagram, videos for TikTok/YouTube, etc.)
- Scheduling window constraints (minimum time in future, timezone handling)
- Platform-specific formatting requirements  
**Outputs:** Platform validation results added to Pre-flight Checks  
**Agent-Function:** `validate_platform_rules(post_id: str, platforms: List[str]) -> Dict[str, Any]`

### Step 4: Scheduling Decision
**Agent Role:** User (Manual) or Agent-Workflow (Automated with user override)  
**Description:** Confirm or adjust scheduled publish date/time based on validation and platform rules.  
**Inputs:** Scheduled Publish Date/Time, Timezone, Platform rules  
**Validation:** Scheduled time must be in future, timezone is valid, meets platform minimum scheduling window  
**Outputs:** Final Scheduled Publish Date/Time, Publication Date Timezone  
**Agent-Function:** `confirm_scheduling(post_id: str, scheduled_time: datetime, timezone: str) -> Dict[str, str]`

### Step 5: Metricool Payload Preparation
**Agent Role:** Agent-Workflow (Automated)  
**Description:** Build Metricool API request payload with all required fields, media IDs, and authentication.  
**Inputs:** Post page ID, Metricool Brand ID, Metricool User ID, Metricool User Token, Caption, Media IDs, Platform(s), Scheduled time  
**Validation:** All required Metricool fields are populated, media IDs are valid (if media required)  
**Outputs:** Metricool API request payload (stored temporarily, logged in API Call History)  
**Agent-Function:** `prepare_metricool_payload(post_id: str) -> Dict[str, Any]`

### Step 6: API Call / Scheduling
**Agent Role:** Agent-Workflow (Automated)  
**Description:** Execute Metricool API call to schedule or publish post, handle response and errors.  
**Inputs:** Metricool API request payload, Metricool API endpoint, authentication headers  
**Validation:** API call is successful (200/201 response) or handled error (400/401/500 with retry logic)  
**Processing:**
- Update Sync Status to "API_CALL_PENDING" before call
- Execute API call with retry logic (exponential backoff on 429/500 errors)
- Parse response to extract Metricool Post ID
- Update Status, Post Status, Sync Status based on response
- If successful: Sync Status = "METRICOOL_SCHEDULED" or "METRICOOL_PUBLISHED", Post Status = "scheduled" or "published"
- If failed: Sync Status = "METRICOOL_FAILED", Post Status = "failed", Last Error Details populated, Retry Count incremented  
**Outputs:** Metricool Post ID (if successful), Metricool Response Data (raw JSON), updated Status/Sync Status/Post Status  
**Agent-Function:** `execute_metricool_api_call(post_id: str, payload: Dict[str, Any]) -> Dict[str, Any]`

### Step 7: Post-Run Logging & Evidence
**Agent Role:** Agent-Workflow (Automated)  
**Description:** Log all execution details, update evidence fields, record state changes for audit trail.  
**Inputs:** Post page ID, execution results, API response, state changes  
**Processing:**
- Update Metricool Sync Log with human-readable execution summary
- Update API Call History with request/response details and timestamp
- Update Last Sync Time to current timestamp
- Update Post Performance Data if post was published (initial analytics snapshot)
- Link execution evidence (Pre-flight Checks, Metricool Response Data, state changes)  
**Outputs:** Updated Metricool Sync Log, API Call History, Last Sync Time, evidence bundle  
**Agent-Function:** `log_execution_evidence(post_id: str, execution_results: Dict[str, Any]) -> None`

## Success Criteria & Validation Surfaces

### Success Criteria (All Must Pass)

**Field Completeness:**
- All required fields are populated (Name, Caption, Platform(s), Scheduled Publish Date/Time, Metricool Brand ID, Metricool User ID, Metricool User Token)
- Validation Status = "Validated"
- Pre-flight Checks show no validation errors

**Media Readiness (if media required):**
- Media Processing Status = "Uploaded"
- Metricool Media IDs are populated (for media posts)
- Photos/Videos relations are valid and non-archived

**API Execution:**
- Metricool API call completed (success or handled error)
- Metricool Response Data is populated
- If successful: Metricool Post ID is populated, Sync Status = "METRICOOL_SCHEDULED" or "METRICOOL_PUBLISHED"
- If failed: Last Error Details populated, Sync Status = "METRICOOL_FAILED", error is actionable

**State Consistency:**
- Status matches Post Status and Sync Status (e.g., Status="Done", Post Status="published", Sync Status="METRICOOL_PUBLISHED")
- Last Sync Time is updated to execution timestamp
- All status changes are logged with timestamps

**Evidence Completeness:**
- Metricool Sync Log contains human-readable execution summary
- API Call History contains request/response details
- Pre-flight Checks contain validation results
- All required evidence fields are populated

### Validation Surfaces

**Data Quality Views (Social-Media-Posts Database):**
- View: Posts with missing required fields (Status filter: "READY TO POST", Validation Status filter: "Invalid" or "Pending")
- View: Posts with broken relations (relation properties empty or pointing to archived records)
- View: Posts with media processing failures (Media Processing Status = "Failed")
- View: Posts with sync errors (Sync Status = "ERROR" or "METRICOOL_FAILED")

**Relation Integrity Views:**
- View: Posts with invalid Client relations (Clients relation empty or archived)
- View: Posts with invalid Photo/Video relations (Photos/Videos relation pointing to archived or missing records)
- View: Posts with invalid Project relations (Project relation pointing to archived or missing records)

**Execution Success Views:**
- View: Successfully scheduled posts (Sync Status = "METRICOOL_SCHEDULED", Post Status = "scheduled")
- View: Successfully published posts (Sync Status = "METRICOOL_PUBLISHED", Post Status = "published", Status = "Done")
- View: Posts pending retry (Sync Status = "METRICOOL_FAILED", Retry Count < 3)

**Governance Views:**
- View: Posts with validation errors (Validation Status = "Invalid" or "Error")
- View: Posts requiring user action (Status = "READY TO POST", Validation Status = "Pending")
- View: Posts with API errors requiring investigation (Sync Status = "METRICOOL_FAILED", Last Error Details populated)

## Dependencies

### External Dependencies
- **Metricool API**: Requires active Metricool account, valid Brand ID, User ID, and User Token
- **Social-Media-Posts Database**: Must exist with proper schema and required properties
- **Related Databases**: Clients, Projects, Photos, Videos, Video Library databases must exist and be accessible

### Internal Dependencies
- **Agent-Workflow Implementation**: This User-Workflow must have a corresponding Agent-Workflow that implements the 7 steps above
- **Agent-Functions**: Each step requires corresponding Agent-Function implementations:
  - `select_draft_posts_for_publication`
  - `validate_post_requirements`
  - `validate_platform_rules`
  - `confirm_scheduling`
  - `prepare_metricool_payload`
  - `execute_metricool_api_call`
  - `log_execution_evidence`
- **Metricool API Client**: Requires Metricool API client library/module with authentication and API call methods
- **Notion API Client**: Requires Notion API client for querying/updating Social-Media-Posts database

### Related Workflows
- **Media Processing Workflow**: Must complete before Step 2 (Media Readiness Validation) if media is required
- **Content Creation Workflow**: Must complete before Step 1 (Intake & Selection) to generate draft posts
- **Post Performance Analytics Workflow**: Executes after Step 7 to capture post performance metrics

## Documentation & Links

### Related Notion Pages
- **Social-Media-Posts Database**: [Notion Database](https://www.notion.so/224e73616c27806abe41dfcf338c0624)
- **Metricool Integration Documentation**: (Link to Metricool API docs and integration guide if available)
- **Agent-Workflow Implementation**: (Link to corresponding Agent-Workflow page when created)
- **Related Issues**: [Workflow Specification Gaps Issue](https://www.notion.so/4c2ab5804f46411bba1df886a3ab0225)

### Related Code/Scripts
- **Metricool API Client**: `shared_core/metricool_api_client.py` (if exists) or `scripts/metricool_notion_sync_runner.py`
- **Notion API Helpers**: `shared_core/notion/` modules for database querying and page updates

### Related Databases
- **Social-Media-Posts**: `224e7361-6c27-806a-be41-dfcf338c0624`
- **Clients**: `20fe7361-6c27-8100-a2ae-e337bfdcb535`
- **Projects**: `286e7361-6c27-81ff-a450-db2ecad4b0ba`
- **Photos**: `223e7361-6c27-80f2-98ed-e1c531c68c2a`
- **Video Library**: `20fe7361-6c27-81ed-94c1-f88f49f5f628`

---

**Last Updated:** 2026-01-10  
**Status:** Draft - Awaiting Review & Implementation  
**Next Steps:**
1. Review and refine Workflow Requirements with stakeholders
2. Create corresponding Agent-Workflow page
3. Implement Agent-Functions for each step
4. Test workflow with sample posts
5. Document execution results and refine requirements based on feedback
