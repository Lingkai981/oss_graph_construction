# Spec Kit Usage Guide

This guide will help you use Spec Kit for spec-driven development in the OSS Graph Construction project.

## Quick Start

### 1. Open Project in Cursor

Make sure you have the `oss_graph_construction` project open in Cursor IDE.

### 2. Verify Commands Available

In Cursor's AI chat interface, you should see the following commands:
- `/speckit.constitution` - Establish project principles
- `/speckit.specify` - Create feature specification
- `/speckit.clarify` - Clarify requirements
- `/speckit.plan` - Create technical plan
- `/speckit.tasks` - Generate task list
- `/speckit.implement` - Execute implementation
- `/speckit.analyze` - Analyze consistency
- `/speckit.checklist` - Generate checklist

## Complete Workflow

### Step 1: Establish Project Principles (First Time)

**Command**: `/speckit.constitution`

**Example**:
```
/speckit.constitution Establish development principles for OSS graph construction project:
- Use Agent-Kernel framework for multi-agent system development
- Follow modular design, each plugin independently testable
- Use Python 3.11+, follow PEP 8 code standards
- All new features must include unit tests
- Configuration files use YAML format
- Logs are written to logs/ directory
```

This creates or updates the `.specify/memory/constitution.md` file.

### Step 2: Create Feature Specification

**Command**: `/speckit.specify`

**Important**: 
- Focus on **what** and **why**, not technical implementation details
- Describe user needs and business goals

**Example**:
```
/speckit.specify Add graph visualization system for OSS project relationships. The system should display contributor networks, project dependencies, and collaboration patterns. Users should be able to filter by project, contributor role, and time period. The visualization should support interactive exploration with zoom, pan, and node selection capabilities.
```

**Automatic operations**:
- ✅ Creates new Git branch (e.g., `001-graph-visualization`)
- ✅ Creates specification directory `specs/001-graph-visualization/`
- ✅ Generates `spec.md` file
- ✅ Switches to new branch

### Step 3: Clarify Requirements (Optional but Recommended)

**Command**: `/speckit.clarify`

Clarify any ambiguous requirements before creating a technical plan:

```
/speckit.clarify Please clarify:
- What graph layout algorithm should be used?
- Should the visualization be real-time or batch-generated?
- What file format should be used for graph data export?
```

### Step 4: Create Technical Implementation Plan

**Command**: `/speckit.plan`

Now specify the tech stack and architecture choices:

```
/speckit.plan Implement using Agent-Kernel framework:
- Create a new OSSGraphPlugin plugin
- Use NetworkX for graph data structures
- Use Plotly or D3.js for visualization (web-based)
- Store graph data in SQLite database (in data/graphs/ directory)
- Provide RESTful API for graph queries
- Use pytest for unit testing
```

**Generated files**:
- `specs/001-graph-visualization/plan.md` - Implementation plan
- `specs/001-graph-visualization/data-model.md` - Data model
- `specs/001-graph-visualization/research.md` - Technical research
- `specs/001-graph-visualization/contracts/` - API contracts (if any)

### Step 5: Generate Task List

**Command**: `/speckit.tasks`

Break down the implementation plan into executable tasks:

```
/speckit.tasks
```

**Generated file**:
- `specs/001-graph-visualization/tasks.md` - Detailed task list

### Step 6: Analyze Consistency (Optional)

**Command**: `/speckit.analyze`

Check consistency between specification, plan, and tasks before implementation:

```
/speckit.analyze
```

### Step 7: Execute Implementation

**Command**: `/speckit.implement`

Let the AI assistant execute the implementation according to the task list:

```
/speckit.implement
```

**Note**: The AI will execute actual code generation and file creation. Make sure you have required tools installed (Python, pytest, etc.).

## Example for OSS Graph Construction Project

### Example: Add Graph Analysis Feature

```
# Step 1: Create specification
/speckit.specify Add graph analysis feature that can identify key contributors, detect community clusters, and analyze project dependency chains. The analysis should support both static snapshots and temporal evolution analysis.

# Step 2: Create plan
/speckit.plan Use Agent-Kernel framework:
- Create OSSGraphAnalysisPlugin
- Use NetworkX for graph algorithms (centrality, community detection)
- Integrate with OSSRelationPlugin for data access
- Provide analysis results via API endpoints
- Store analysis results in data/analysis/ directory

# Step 3: Generate tasks and implement
/speckit.tasks
/speckit.implement
```

## Git Workflow

Each time you use `/speckit.specify`:

1. **Automatic branch creation**: e.g., `001-feature-name`
2. **Specification files**: Saved in `specs/001-feature-name/` directory
3. **After development**:
   ```bash
   git add .
   git commit -m "Implement feature: graph visualization system"
   git push origin 001-graph-visualization
   ```
4. **Create Pull Request**: Create PR on GitHub for code review

## Best Practices

1. **Spec first, code later**: Use `/speckit.specify` to describe requirements, don't jump directly to implementation
2. **Iterate and refine**: Use `/speckit.clarify` to clarify ambiguous points
3. **Follow principles**: Ensure implementation follows principles defined in `/speckit.constitution`
4. **Test first**: Ensure test plans are clear before implementation
5. **Keep docs in sync**: Specification files stay synchronized with code as they generate it

## Troubleshooting

### Commands Not Visible
- Make sure you're in the project root directory in Cursor
- Check if `.cursor/commands/` directory exists
- Restart Cursor IDE

### Git Branch Creation Failed
- Ensure Git repository is initialized
- Check for uncommitted changes
- Run `git fetch --all` to update remote branch information

### Script Execution Failed
- Ensure scripts have execute permissions: `chmod +x .specify/scripts/bash/*.sh`
- Check if you're executing from project root directory

## More Resources

- [Spec Kit Official Documentation](https://github.github.io/spec-kit/)
- [Spec-Driven Development Methodology](../spec-kit/spec-driven.md)
- [GitHub Project](https://github.com/github/spec-kit)

---

**Get Started**: Open AI chat in Cursor, type `/speckit.constitution` to begin your first spec-driven development!

