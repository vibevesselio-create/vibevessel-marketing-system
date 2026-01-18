# Agent-Function Assignments Population Guide

**Date:** 2025-01-29  
**Status:** Ready for Execution  
**Script:** `scripts/populate_agent_function_assignments.py`

---

## Executive Summary

This guide explains how to populate missing Execution-Agent and Review-Agent assignments in the Agent-Functions database based on function purpose, capabilities, and system-designated agent roles following the Universal Four-Agent Coordination Workflow.

---

## Problem Statement

A compliance review found that **238 Agent-Function items** (100%) are missing both Execution-Agent and Review-Agent assignments. This prevents:
- Proper routing of functions to execution and review agents
- Handoff task generation from identifying appropriate agents
- Agent-Functions compliance requirements from being met

---

## Agent Capabilities & Roles

### Cursor MM1 Agent
**Agent ID:** `249e7361-6c27-8100-8a74-de7eabb9fc8d`

**Capabilities:**
- Code generation and implementation
- Technical development (Python, JavaScript, GAS)
- Script creation and modification
- Testing and validation
- Bug fixes and error handling
- API integrations
- Automation scripts
- Production deployment

**Keywords:** code, implementation, script, technical, development, programming, gas, python, javascript, testing, deploy, fix, bug, error, function, class, api, integration, sync, automation, execution, build

**Typical Review-Agent:** Claude MM1 (code review, quality assurance)

---

### Claude MM1 Agent
**Agent ID:** `fa54f05c-e184-403a-ac28-87dd8ce9855b`

**Capabilities:**
- Review and quality assurance
- Coordination and orchestration
- Validation and compliance checking
- Documentation (Diátaxis-compliant)
- MCP/Agent coordination
- Workflow management
- Protocol enforcement
- Pre-flight validation
- Meta-analysis and auditing

**Keywords:** review, coordination, validation, audit, compliance, analysis, documentation, diátaxis, quality assurance, integration, orchestration, handoff, workflow, protocol, compliance check, verify, validate, research, investigation, assessment, evaluation, mcp, agent coordination

**Typical Review-Agent:** Cursor MM1 (technical validation) or ChatGPT (strategic validation)

---

### ChatGPT (OpenAI)
**Agent ID:** `9c4b6040-5e0f-4d31-ae1b-d4a43743b224`

**Capabilities:**
- Strategic planning and analysis
- Architectural guidance
- Requirements clarification
- Discovery and audit
- Methodology design
- Roadmap creation
- High-level recommendations

**Keywords:** strategic, planning, architecture, design, strategy, roadmap, analysis, recommendation, guidance, approach, methodology, discovery, audit, requirements, clarification, architectural

**Typical Review-Agent:** Claude MM1 (strategic review, validation)

---

### Notion AI Data Operations
**Agent ID:** `2d9e7361-6c27-80c5-ba24-c6f847789d77`

**Capabilities:**
- Data operations and updates
- Database schema work
- Notion workspace updates
- Data entry and synchronization
- Registry maintenance
- Metadata management
- Property and relation management
- Query operations

**Keywords:** data, database, schema, notion, workspace, update, entry, sync, registry, metadata, properties, relation, query, notion database, data source, data_source, workspace database, page, block

**Typical Review-Agent:** Claude MM1 (data validation, compliance)

---

### Notion AI Research
**Agent ID:** `2d9e7361-6c27-80c5-ba24-c6f847789d77` (may be same as Data Ops)

**Capabilities:**
- Documentation synthesis
- Research analysis
- Report generation
- Documentation gap analysis

**Keywords:** documentation, synthesis, research, analysis, report, summary, notion-ai-research, research agent, documentation gap

**Typical Review-Agent:** Claude MM1 (documentation review)

---

## Assignment Logic

The script uses keyword matching and heuristics to determine appropriate agent assignments:

### Execution-Agent Priority Order:

1. **Notion-specific operations** → Notion AI Data Operations
   - Database, schema, workspace, data sync operations

2. **Strategic/Planning work** → ChatGPT
   - Strategic planning, architecture, discovery, audit

3. **Code/Implementation work** → Cursor MM1
   - Scripts, code, technical development, GAS, automation

4. **Review/Coordination/Validation** → Claude MM1
   - Review, coordination, validation, compliance, MCP/agent coordination

5. **Research/Documentation** → Notion AI Research/Data Ops
   - Documentation, synthesis, research analysis

6. **Default fallback:**
   - Technical keywords → Cursor MM1
   - Analytical keywords → Claude MM1
   - Otherwise → Claude MM1 (coordination/analysis)

### Review-Agent Assignment Rules:

- **Cursor work** → Claude MM1 (code review, quality assurance)
- **ChatGPT work** → Claude MM1 (strategic review, validation)
- **Notion AI Data Ops** → Claude MM1 (data validation, compliance)
- **Claude work** → Cursor MM1 (technical validation) or ChatGPT (strategic validation)
- **Notion AI Research** → Claude MM1 (documentation review)

---

## Usage

### Step 1: Set Up Environment

```bash
export NOTION_TOKEN="your_notion_token_here"
# OR
export NOTION_API_KEY="your_notion_token_here"
```

### Step 2: Run in Dry-Run Mode (Recommended First)

```bash
cd /Users/brianhellemn/Projects/github-production
python3 scripts/populate_agent_function_assignments.py --dry-run
```

This will show what assignments would be made without actually updating Notion.

### Step 3: Review Output

The script will show:
- Each Agent-Function item being processed
- Current assignment status (missing both, missing execution, missing review, or complete)
- Proposed assignments
- Summary statistics

### Step 4: Run for Real

```bash
python3 scripts/populate_agent_function_assignments.py
```

This will update all Agent-Function items with appropriate agent assignments.

---

## Example Output

```
🚀 Populating Agent-Function Assignments...

================================================================================
Found 238 Agent-Function items

📝 DriveSheetsSync Production Readiness Review
   Missing: Both Execution-Agent and Review-Agent
   Assigning: Execution=249e7361..., Review=fa54f05c...
   ✅ Updated

📝 Agent-Functions Compliance Check
   Missing: Both Execution-Agent and Review-Agent
   Assigning: Execution=fa54f05c..., Review=249e7361...
   ✅ Updated

...

================================================================================
SUMMARY
================================================================================
Total items: 238
Already complete: 0
Missing both: 238
Missing Execution-Agent only: 0
Missing Review-Agent only: 0
Updated: 238
Errors: 0

✅ Updated 238 Agent-Function items
```

---

## Assignment Examples

### Example 1: Code/Implementation Function
**Function:** "Create GAS Script for Database Sync"  
**Description:** "Generate Google Apps Script code to sync Notion databases to Google Sheets"  
**Assignment:**
- Execution-Agent: Cursor MM1 Agent (code generation)
- Review-Agent: Claude MM1 Agent (code review)

### Example 2: Strategic Planning Function
**Function:** "Strategic Analysis for Workflow Enhancement"  
**Description:** "Analyze current workflow and provide strategic recommendations for improvement"  
**Assignment:**
- Execution-Agent: ChatGPT (strategic planning)
- Review-Agent: Claude MM1 Agent (strategic review)

### Example 3: Data Operations Function
**Function:** "Update Notion Database Schema"  
**Description:** "Update schema properties in Notion database based on CSV template"  
**Assignment:**
- Execution-Agent: Notion AI Data Operations (data operations)
- Review-Agent: Claude MM1 Agent (data validation)

### Example 4: Review/Coordination Function
**Function:** "Agent-Functions Compliance Check"  
**Description:** "Review Agent-Functions database for compliance with Execution-Agent and Review-Agent requirements"  
**Assignment:**
- Execution-Agent: Claude MM1 Agent (compliance review)
- Review-Agent: Cursor MM1 Agent (technical validation)

---

## Verification

After running the script, verify assignments:

1. **Check Notion Agent-Functions Database:**
   - All items should have Execution-Agent assigned
   - All items should have Review-Agent assigned

2. **Run Compliance Check:**
   ```bash
   python3 scripts/review_agent_functions_compliance.py
   ```
   - Should show 0 items missing assignments

3. **Review Sample Items:**
   - Check a few items manually to ensure assignments make sense
   - Verify agent capabilities match function purpose

---

## Troubleshooting

### Issue: NOTION_TOKEN not set
**Solution:** Export NOTION_TOKEN or NOTION_API_KEY environment variable

### Issue: Some assignments seem incorrect
**Solution:** 
1. Review the function name and description
2. Check if keywords match agent capabilities
3. Manually update specific items in Notion if needed
4. Consider refining keyword lists in the script

### Issue: Script fails with API errors
**Solution:**
- Check Notion API token is valid
- Verify database ID is correct: `256e73616c2780c783facd029ff49d2d`
- Check API rate limits (script handles pagination automatically)

### Issue: Agent IDs not found
**Solution:** Verify agent IDs exist in Agents database:
- Cursor MM1: `249e7361-6c27-8100-8a74-de7eabb9fc8d`
- Claude MM1: `fa54f05c-e184-403a-ac28-87dd8ce9855b`
- ChatGPT: `9c4b6040-5e0f-4d31-ae1b-d4a43743b224`
- Notion AI Data Ops: `2d9e7361-6c27-80c5-ba24-c6f847789d77`

---

## Manual Overrides

If automatic assignments need correction:

1. **In Notion:**
   - Open the Agent-Function item
   - Update Execution-Agent and Review-Agent relations manually
   - Document reason for override in item description

2. **For Future Items:**
   - Ensure function name and description include appropriate keywords
   - Follow naming conventions that match agent capabilities

---

## Next Steps

After populating assignments:

1. ✅ Run compliance check to verify all items have assignments
2. ✅ Review sample items to ensure assignments are appropriate
3. ✅ Update any incorrect assignments manually if needed
4. ✅ Document any patterns or exceptions discovered
5. ✅ Update keyword lists if common patterns are missed

---

## References

- **Universal Four-Agent Coordination Workflow:** https://www.notion.so/serenmedia/Universal-Four-Agent-Coordination-Workflow-462a2e8561184399bcb985caa786977e
- **Agent-Functions Compliance Review:** `scripts/review_agent_functions_compliance.py`
- **Compliance Issues:** `scripts/create_compliance_issues.py`

---

**Last Updated:** 2025-01-29  
**Status:** Ready for Execution












































































































