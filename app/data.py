"""Fictional sessions created for this demo, not an official conference schedule."""

ROWS = [
    ("Kubernetes Without the Jargon", "Maya Chen", "Kubernetes", "beginner", "09:00", "09:45", "Start with pods, deployments and services in this plain-language Kubernetes introduction.", ["kubernetes", "beginner", "containers"]),
    ("Your First Threat Model", "Ibrahim Ali", "Security", "beginner", "09:00", "09:45", "Map cloud-native security threats before shipping your first workload.", ["security", "beginner", "threat modeling"]),
    ("Tracing a Request Across Services", "Ava Brooks", "Observability", "intermediate", "09:00", "09:45", "Use OpenTelemetry traces to follow a request and find latency in distributed services.", ["observability", "opentelemetry", "tracing"]),
    ("Shipping a Platform Developers Love", "Noah Singh", "Platform", "intermediate", "09:00", "09:45", "Design a developer platform around feedback, golden paths and measurable outcomes.", ["platform", "developer experience"]),
    ("Lock Down Your Kubernetes Cluster", "Sofia Patel", "Security", "beginner", "10:00", "10:45", "A beginner guide to Kubernetes security with RBAC, namespaces and safe defaults.", ["kubernetes", "security", "beginner", "rbac"]),
    ("Metrics That Explain User Pain", "Leo Okafor", "Observability", "beginner", "10:00", "10:45", "Pick useful service metrics and build a dashboard for latency and errors.", ["observability", "metrics", "beginner"]),
    ("GitOps From Commit to Cluster", "Emma Rivera", "Platform", "intermediate", "10:00", "10:45", "Deploy Kubernetes applications safely using reconciliation and GitOps workflows.", ["kubernetes", "gitops", "deployment"]),
    ("Vector Search in Practice", "Kai Williams", "Data", "intermediate", "10:00", "10:45", "Combine keyword relevance and vector retrieval in Elasticsearch for useful discovery.", ["elasticsearch", "search", "vectors"]),
    ("Network Policies by Example", "Zara Ahmed", "Security", "intermediate", "11:00", "11:45", "Reduce lateral movement with practical Kubernetes network security policies.", ["kubernetes", "security", "networking"]),
    ("Debugging Kubernetes With Confidence", "Oliver Kim", "Kubernetes", "beginner", "11:00", "11:45", "Read events, inspect logs and resolve common pod failures step by step.", ["kubernetes", "beginner", "debugging"]),
    ("Service Level Objectives for Humans", "Grace Mensah", "Observability", "beginner", "11:00", "11:45", "Connect error budgets and service level objectives to your users' experience.", ["observability", "slo", "beginner"]),
    ("Streaming Data Without Surprises", "Ethan Park", "Data", "advanced", "11:00", "11:45", "Handle backpressure, ordering and replay in cloud-native event pipelines.", ["data", "streaming", "kafka"]),
    ("Supply Chain Security Starter Kit", "Amara Jones", "Security", "beginner", "12:00", "12:45", "Make container builds safer with image signing, provenance and dependency checks.", ["security", "beginner", "containers", "supply chain"]),
    ("Autoscaling Beyond CPU", "Liam Ndlovu", "Kubernetes", "intermediate", "12:00", "12:45", "Scale Kubernetes workloads using queues and custom business metrics.", ["kubernetes", "autoscaling", "metrics"]),
    ("A Better On-Call Handoff", "Isla Garcia", "Observability", "intermediate", "12:00", "12:45", "Turn telemetry into useful incident context with clear ownership and runbooks.", ["observability", "incidents", "on-call"]),
    ("Accessible Developer Portals", "Arjun Das", "Platform", "beginner", "12:00", "12:45", "Build keyboard-friendly, readable developer portals and inclusive documentation.", ["platform", "accessibility", "beginner"]),
    ("Secrets Without Spreadsheets", "Nia Robinson", "Security", "beginner", "14:00", "14:45", "Rotate credentials and distribute secrets safely to Kubernetes applications.", ["security", "kubernetes", "beginner", "secrets"]),
    ("Inside the Kubernetes Scheduler", "Lucas Nguyen", "Kubernetes", "advanced", "14:00", "14:45", "Understand scheduling constraints, affinity and resource-aware placement.", ["kubernetes", "scheduling", "performance"]),
    ("eBPF for Service Visibility", "Freya Wilson", "Observability", "advanced", "14:00", "14:45", "Observe kernel events and understand service behavior with eBPF instrumentation.", ["observability", "ebpf", "linux"]),
    ("Search Relevance You Can Explain", "Mateo Silva", "Data", "beginner", "14:00", "14:45", "Tune Elasticsearch field boosts and filters to make keyword search useful.", ["elasticsearch", "search", "beginner"]),
    ("Admission Policies That Help", "Aisha Khan", "Security", "intermediate", "15:00", "15:45", "Enforce Kubernetes security policy with helpful feedback instead of surprise failures.", ["kubernetes", "security", "policy"]),
    ("Your First Kubernetes Operator", "Theo Martin", "Kubernetes", "beginner", "15:00", "15:45", "Build a simple reconciliation loop and understand custom resources.", ["kubernetes", "beginner", "operators"]),
    ("Find the Slow Query", "Chloe Evans", "Observability", "intermediate", "15:00", "15:45", "Use traces and database metrics to isolate a slow search request.", ["observability", "search", "performance"]),
    ("FinOps for Small Teams", "Ravi Shah", "Platform", "beginner", "15:00", "15:45", "Understand cloud spending and reduce waste without sacrificing reliability.", ["platform", "cost", "beginner"]),
    ("Security Lessons From an Incident", "Ada Thompson", "Security", "intermediate", "16:00", "16:45", "Walk through a Kubernetes credential leak and the controls that limited impact.", ["security", "kubernetes", "incidents"]),
    ("Resilient Apps on Kubernetes", "Finn Taylor", "Kubernetes", "beginner", "16:00", "16:45", "Add probes, graceful shutdown and disruption budgets to keep services available.", ["kubernetes", "beginner", "reliability"]),
    ("Telemetry Without the Bill Shock", "Yuki Sato", "Observability", "intermediate", "16:00", "16:45", "Control cardinality and sampling while preserving useful debugging signals.", ["observability", "cost", "opentelemetry"]),
    ("Postgres in a Cloud-Native World", "Daniel Ortiz", "Data", "intermediate", "16:00", "16:45", "Plan backups, recovery and reliable database operations for container platforms.", ["data", "postgres", "reliability"]),
]

TALKS = [
    {"id": f"talk-{i:02d}", "title": row[0], "speaker": row[1], "track": row[2],
     "level": row[3], "start": f"2026-11-09T{row[4]}:00-07:00",
     "end": f"2026-11-09T{row[5]}:00-07:00", "room": ["Summit", "Canyon", "Aspen", "Mesa"][(i - 1) % 4],
     "description": row[6], "tags": row[7],
     "accessibility": {"captioned": i % 5 != 0, "step_free": i % 7 != 0,
                       "plain_language_summary": row[3] == "beginner"}}
    for i, row in enumerate(ROWS, 1)
]
