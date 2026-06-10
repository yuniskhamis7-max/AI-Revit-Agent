# Dependency Management

<cite>
**Referenced Files in This Document**
- [dependency.py](file://planner/dependency.py)
- [planner.py](file://planner/planner.py)
- [executor.py](file://planner/executor.py)
- [visualizer.py](file://planner/visualizer.py)
- [runtime_executor.py](file://runtime/executor.py)
- [workflow.py](file://runtime/workflow.py)
- [__init__.py](file://planner/__init__.py)
- [README.md](file://README.md)
</cite>

## Table of Contents
1. [Introduction](#introduction)
2. [Project Structure](#project-structure)
3. [Core Components](#core-components)
4. [Architecture Overview](#architecture-overview)
5. [Detailed Component Analysis](#detailed-component-analysis)
6. [Dependency Analysis](#dependency-analysis)
7. [Performance Considerations](#performance-considerations)
8. [Troubleshooting Guide](#troubleshooting-guide)
9. [Conclusion](#conclusion)
10. [Appendices](#appendices)

## Introduction
This document explains the dependency management system that constructs, validates, and orders execution steps for deterministic workflows. It covers:
- Dependency graph construction and validation
- Cycle detection to prevent circular dependencies
- Topological sorting for safe execution order
- Dependency validation ensuring referenced steps exist and form valid acyclic graphs
- Examples of explicit dependencies versus automatic sequential dependencies
- Conflict resolution strategies and debugging guidance
- Integration with the broader planning and runtime systems

The dependency layer is intentionally decoupled from Revit execution concerns to enable testing, reuse, and early failure detection.

## Project Structure
The dependency management spans the planner and runtime layers:
- Planner: plan generation, dependency validation, topological ordering, and plan visualization
- Runtime: plan approval flow, dependency validation, and step-by-step execution with failure propagation
- Workflow: payload dispatch and deterministic BIM operations

```mermaid
graph TB
subgraph "Planner Layer"
D["dependency.py<br/>Graph validation, ordering, helpers"]
P["planner.py<br/>Plan generation, validation, ordering"]
E["executor.py<br/>Plan execution, failure propagation"]
V["visualizer.py<br/>Text rendering of plan and order"]
end
subgraph "Runtime Layer"
RE["runtime/executor.py<br/>Human-in-the-loop flow"]
WF["runtime/workflow.py<br/>Payload dispatch and execution"]
end
RE --> P
P --> D
P --> V
E --> WF
RE --> E
```

**Diagram sources**
- [dependency.py:18-224](file://planner/dependency.py#L18-L224)
- [planner.py:35-234](file://planner/planner.py#L35-L234)
- [executor.py:40-227](file://planner/executor.py#L40-L227)
- [visualizer.py:20-169](file://planner/visualizer.py#L20-L169)
- [runtime_executor.py:133-225](file://runtime/executor.py#L133-L225)
- [workflow.py:84-235](file://runtime/workflow.py#L84-L235)

**Section sources**
- [README.md:14-35](file://README.md#L14-L35)
- [__init__.py:1-18](file://planner/__init__.py#L1-L18)

## Core Components
- Dependency graph validation: checks missing dependencies, self-dependencies, and cycles
- Topological ordering: Kahn’s algorithm to compute deterministic execution order
- Dependents computation: direct and transitive dependents for failure propagation
- Plan generation: builds steps from payloads with default sequential dependencies or explicit dependencies
- Plan execution: runs steps in topological order, propagates failures, and reports results
- Visualization: renders dependency graph and execution order for human review

Key responsibilities:
- Pure reasoning layer: dependency.py operates on step dictionaries without Revit imports
- Deterministic planning: planner.py ensures reproducible plans and orders
- Failure propagation: planner.executor enforces safe downstream skipping when upstream steps fail
- Human-in-the-loop approval: runtime.executor coordinates plan preview, approval, and execution

**Section sources**
- [dependency.py:18-224](file://planner/dependency.py#L18-L224)
- [planner.py:35-234](file://planner/planner.py#L35-L234)
- [executor.py:40-227](file://planner/executor.py#L40-L227)
- [visualizer.py:20-169](file://planner/visualizer.py#L20-L169)
- [runtime_executor.py:133-225](file://runtime/executor.py#L133-L225)

## Architecture Overview
The dependency management integrates across layers to ensure safe, deterministic execution.

```mermaid
sequenceDiagram
participant User as "User"
participant Runtime as "runtime/executor.py"
participant Planner as "planner/planner.py"
participant Dep as "planner/dependency.py"
participant Exec as "planner/executor.py"
participant WF as "runtime/workflow.py"
User->>Runtime : "Run instruction and execute"
Runtime->>Runtime : "_plan_approve_and_execute()"
Runtime->>Planner : "generate_plan(payloads)"
Planner->>Dep : "topological_order(steps)"
Dep-->>Planner : "ordered step IDs"
Planner-->>Runtime : "plan"
Runtime->>Runtime : "show_plan_preview(plan)"
User-->>Runtime : "approve plan"
Runtime->>Planner : "validate_plan(plan)"
Planner->>Dep : "validate_dependency_graph(steps)"
Dep-->>Planner : "errors or empty"
Planner-->>Runtime : "validation result"
Runtime->>Exec : "execute_plan(plan, document)"
Exec->>Exec : "ordered_steps(plan)"
loop "for each step in order"
Exec->>WF : "dispatch_fn(payload)"
WF-->>Exec : "result"
Exec->>Exec : "_propagate_failure(step) if needed"
end
Exec-->>Runtime : "plan_result(executed_plan)"
Runtime-->>User : "show_plan_result(result)"
```

**Diagram sources**
- [runtime_executor.py:133-225](file://runtime/executor.py#L133-L225)
- [planner.py:35-92](file://planner/planner.py#L35-L92)
- [dependency.py:52-72](file://planner/dependency.py#L52-L72)
- [executor.py:40-95](file://planner/executor.py#L40-L95)
- [workflow.py:84-92](file://runtime/workflow.py#L84-L92)

## Detailed Component Analysis

### Dependency Graph Construction and Validation
- Validates each step’s dependencies:
  - Missing dependencies: detects references to non-existent step IDs
  - Self-dependency: detects a step depending on itself
- Detects cycles using depth-first search with recursion stack; returns one cycle path if found
- Provides human-readable dependency graph text and logs execution order for diagnostics

```mermaid
flowchart TD
Start(["validate_dependency_graph(steps)"]) --> Collect["Collect all step IDs"]
Collect --> LoopSteps["For each step"]
LoopSteps --> CheckMissing["Find missing dependencies"]
CheckMissing --> AddMissingErr["Add 'missing dependency' error"]
LoopSteps --> CheckSelf["Check self-dependency"]
CheckSelf --> AddSelfErr["Add 'self-dependency' error"]
LoopSteps --> NextStep{"More steps?"}
NextStep --> |Yes| LoopSteps
NextStep --> |No| DetectCycle["_detect_cycle(steps)"]
DetectCycle --> HasCycle{"Cycle found?"}
HasCycle --> |Yes| AddCycleErr["Add 'cycle detected' error"]
HasCycle --> |No| Done(["Return errors"])
```

**Diagram sources**
- [dependency.py:18-49](file://planner/dependency.py#L18-L49)
- [dependency.py:155-172](file://planner/dependency.py#L155-L172)

**Section sources**
- [dependency.py:18-49](file://planner/dependency.py#L18-L49)
- [dependency.py:155-194](file://planner/dependency.py#L155-L194)

### Topological Ordering Implementation
- Uses Kahn’s algorithm:
  - Build adjacency list from dependencies
  - Compute in-degree for each step
  - Seed queue with steps having zero in-degree
  - Iteratively remove nodes and reduce in-degree of neighbors
  - Tie-breaking preserves original input order for determinism

```mermaid
flowchart TD
A["topological_order(steps)"] --> Adj["_build_adjacency(steps)"]
Adj --> Indeg["_build_in_degree(steps)"]
Indeg --> Seed["_initial_queue(steps, in_degree)"]
Seed --> WhileQ{"queue not empty"}
WhileQ --> |pop| Pop["current = queue.pop(0)"]
Pop --> Append["ordered.append(current)"]
Append --> Neigh["for neighbor in adjacency[current]"]
Neigh --> Dec["in_degree[neighbor] -= 1"]
Dec --> Zero{"in_degree[neighbor] == 0?"}
Zero --> |Yes| Enq["queue.append(neighbor)"]
Zero --> |No| WhileQ
Enq --> WhileQ
WhileQ --> |empty| Return["return ordered"]
```

**Diagram sources**
- [dependency.py:52-72](file://planner/dependency.py#L52-L72)
- [dependency.py:197-224](file://planner/dependency.py#L197-L224)

**Section sources**
- [dependency.py:52-72](file://planner/dependency.py#L52-L72)
- [dependency.py:197-224](file://planner/dependency.py#L197-L224)

### Dependents Computation for Failure Propagation
- Direct dependents: steps that list a given step ID in their dependencies
- Transitive dependents: breadth-first traversal of dependents to find all downstream steps affected by upstream failure

```mermaid
flowchart TD
StartD["dependents_of(step_id, steps)"] --> ScanD["Scan steps for 'step_id' in dependencies"]
ScanD --> FoundD["Append matching step_id to result"]
FoundD --> DoneD["Return result"]
StartT["all_dependents_of(step_id, steps)"] --> InitT["visited = set(), queue = [step_id]"]
InitT --> LoopT{"queue not empty"}
LoopT --> |pop| PopT["current = queue.pop(0)"]
PopT --> ScanT["dependents_of(current, steps)"]
ScanT --> AddT{"dep not in visited?"}
AddT --> |Yes| Mark["visited.add(dep); queue.append(dep)"]
AddT --> |No| LoopT
Mark --> LoopT
LoopT --> |empty| ReturnT["Return list(visited)"]
```

**Diagram sources**
- [dependency.py:75-104](file://planner/dependency.py#L75-L104)

**Section sources**
- [dependency.py:75-104](file://planner/dependency.py#L75-L104)

### Plan Generation and Default Dependencies
- Each payload becomes a step with a deterministic step ID
- Default dependency: each step depends on the previous step (sequential ordering)
- Explicit dependencies override defaults; can be provided via a mapping from step_id to dependency list

```mermaid
sequenceDiagram
participant Gen as "generate_plan()"
participant Steps as "_create_steps()"
participant Def as "_default_deps()"
participant Build as "_build_step()"
Gen->>Steps : "create steps from payloads"
Steps->>Def : "compute default deps for index > 0"
Def-->>Steps : "previous step ID"
Steps->>Build : "build step with step_id, deps, payload"
Build-->>Steps : "step dict"
Steps-->>Gen : "steps list"
```

**Diagram sources**
- [planner.py:35-61](file://planner/planner.py#L35-L61)
- [planner.py:146-190](file://planner/planner.py#L146-L190)
- [planner.py:166-177](file://planner/planner.py#L166-L177)

**Section sources**
- [planner.py:35-61](file://planner/planner.py#L35-L61)
- [planner.py:146-190](file://planner/planner.py#L146-L190)
- [planner.py:166-177](file://planner/planner.py#L166-L177)

### Plan Execution and Failure Propagation
- Executes steps in topological order
- Skips steps that already failed/skipped or have failed dependencies
- On failure, marks the step failed and skips all transitive dependents

```mermaid
sequenceDiagram
participant Exec as "execute_plan()"
participant Order as "ordered_steps()"
participant Dispatch as "dispatch_fn()"
participant Prop as "_propagate_failure()"
Exec->>Order : "steps in topological order"
loop "for each step"
Exec->>Exec : "_has_failed_dependency(step)?"
alt "failed dependency"
Exec->>Exec : "_skip_step_with_failed_dep(step)"
else "proceed"
Exec->>Dispatch : "execute payload"
alt "success"
Dispatch-->>Exec : "result.success = True"
Exec->>Exec : "mark_step SUCCESS"
else "failure"
Dispatch-->>Exec : "result.success = False"
Exec->>Exec : "mark_step FAILED"
Exec->>Prop : "propagate failure to dependents"
end
end
end
Exec-->>Exec : "plan_result(executed_plan)"
```

**Diagram sources**
- [executor.py:40-95](file://planner/executor.py#L40-L95)
- [executor.py:135-202](file://planner/executor.py#L135-L202)
- [workflow.py:84-92](file://runtime/workflow.py#L84-L92)

**Section sources**
- [executor.py:40-95](file://planner/executor.py#L40-L95)
- [executor.py:135-202](file://planner/executor.py#L135-L202)
- [workflow.py:84-92](file://runtime/workflow.py#L84-L92)

### Visualization and Logging
- Renders dependency graph and execution order for human review
- Logs dependency graph and order for diagnostics
- Provides plan text and result text for UI alerts

**Section sources**
- [visualizer.py:20-60](file://planner/visualizer.py#L20-L60)
- [dependency.py:125-136](file://planner/dependency.py#L125-L136)

## Dependency Analysis
- Coupling:
  - planner.planner depends on planner.dependency for validation and ordering
  - planner.executor depends on planner.dependency for transitive dependents and on planner.planner for step ordering/status
  - runtime.executor orchestrates planner and runtime.workflow for end-to-end flow
- Cohesion:
  - dependency.py encapsulates all graph-related logic (validation, ordering, helpers)
  - planner.py encapsulates plan structure, status, and ordering
  - executor.py encapsulates execution semantics and failure propagation
  - runtime.executor orchestrates the human-in-the-loop flow
- External dependencies:
  - No Revit imports in planner or dependency layers
  - runtime.executor bridges to runtime.workflow for payload execution

```mermaid
graph LR
Dep["planner/dependency.py"] <-- "validate, order" --> Plan["planner/planner.py"]
Plan <-- "ordered_steps" --> Exec["planner/executor.py"]
Plan <-- "validate_plan" --> RE["runtime/executor.py"]
Exec --> WF["runtime/workflow.py"]
RE --> Plan
RE --> Exec
```

**Diagram sources**
- [dependency.py:18-72](file://planner/dependency.py#L18-L72)
- [planner.py:64-92](file://planner/planner.py#L64-L92)
- [executor.py:40-95](file://planner/executor.py#L40-L95)
- [runtime_executor.py:133-225](file://runtime/executor.py#L133-L225)
- [workflow.py:84-92](file://runtime/workflow.py#L84-L92)

**Section sources**
- [dependency.py:18-72](file://planner/dependency.py#L18-L72)
- [planner.py:64-92](file://planner/planner.py#L64-L92)
- [executor.py:40-95](file://planner/executor.py#L40-L95)
- [runtime_executor.py:133-225](file://runtime/executor.py#L133-L225)
- [workflow.py:84-92](file://runtime/workflow.py#L84-L92)

## Performance Considerations
- Complexity:
  - Dependency validation: O(V + E) for missing/self/cycle checks using adjacency and DFS
  - Topological sort (Kahn): O(V + E) with queue operations
  - Dependents computation: O(V + E) for BFS traversal
- Determinism:
  - Queue initialization and tie-breaking preserve input order for stable results
- Practical tips:
  - Keep dependency graphs sparse; avoid dense fan-out to minimize propagation cost
  - Prefer explicit dependencies only when necessary; default sequential ordering reduces overhead
  - Log and visualize dependency graphs to catch inefficiencies early

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
Common issues and resolutions:
- Missing dependency references:
  - Symptom: Validation error indicating a step depends on a non-existent step ID
  - Resolution: Ensure all referenced step IDs exist; fix typos or omitted steps
- Self-dependency:
  - Symptom: Validation error stating a step depends on itself
  - Resolution: Remove self-reference from dependencies
- Circular dependencies:
  - Symptom: Validation error reporting a cycle path
  - Resolution: Break the cycle by removing or reworking dependencies; reconsider plan structure
- Upstream failure propagation:
  - Symptom: Downstream steps are skipped with a “dependency failed” reason
  - Resolution: Fix the upstream failing step; rerun the plan; verify transitive dependents are intended to be skipped
- Execution order surprises:
  - Symptom: Unexpected step ordering
  - Resolution: Review explicit dependencies; default sequential ordering applies when none provided

Debugging aids:
- Use dependency graph text and execution order logs to inspect relationships
- Visualize the plan before approval to catch structural issues early
- Inspect per-step status and results after execution to trace propagation

**Section sources**
- [dependency.py:18-49](file://planner/dependency.py#L18-L49)
- [dependency.py:155-172](file://planner/dependency.py#L155-L172)
- [executor.py:177-202](file://planner/executor.py#L177-L202)
- [visualizer.py:20-60](file://planner/visualizer.py#L20-L60)
- [dependency.py:125-136](file://planner/dependency.py#L125-L136)

## Conclusion
The dependency management system provides a robust, deterministic foundation for constructing, validating, and ordering execution steps. By separating dependency reasoning from execution, it enables early failure detection, human review, and safe propagation of failures. The integration with the planning and runtime layers ensures that plans are validated before any BIM operations and executed in a controlled, observable manner.

[No sources needed since this section summarizes without analyzing specific files]

## Appendices

### Explicit vs Automatic Dependencies
- Automatic sequential dependencies:
  - Default: each step depends on the previous step
  - Safe for BIM operations where creation order matters (e.g., levels before grids)
- Explicit dependencies:
  - Provided via a mapping from step_id to a list of dependency step IDs
  - Override defaults to express parallelizable or non-sequential relationships

**Section sources**
- [planner.py:166-177](file://planner/planner.py#L166-L177)
- [planner.py:146-157](file://planner/planner.py#L146-L157)

### Integration with Planning and Runtime Systems
- Planning layer:
  - generate_plan builds steps and logs dependency graph
  - validate_plan checks structural correctness and dependency integrity
  - ordered_steps returns steps respecting topological order
- Runtime layer:
  - runtime.executor coordinates plan generation, visualization, approval, dependency validation, and execution
  - runtime.workflow dispatches payloads to deterministic BIM operations

**Section sources**
- [planner.py:35-92](file://planner/planner.py#L35-L92)
- [planner.py:136-142](file://planner/planner.py#L136-L142)
- [runtime_executor.py:133-225](file://runtime/executor.py#L133-L225)
- [workflow.py:84-92](file://runtime/workflow.py#L84-L92)