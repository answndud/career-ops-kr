from __future__ import annotations


# Realistic scoring fixtures derived from public Korean job postings reviewed on
# 2026-04-06. The texts are intentionally anonymized and paraphrased so tests
# stay stable and do not depend on the live posting wording.

REALISTIC_JD_SAMPLES: dict[str, dict[str, str]] = {
    "backend_fintech_saas": {
        "title": "Sr. Backend Engineer",
        "body": (
            "B2B SaaS backend role for a fintech product. Design backend APIs, "
            "authentication and authorization features, and cloud architecture for "
            "a growing SaaS platform. Requires 5+ years of backend experience, "
            "Java or Python service development, AWS infrastructure operation, "
            "distributed systems, Kubernetes, and platform-level capabilities."
        ),
    },
    "devops_security_analytics": {
        "title": "DevOps Engineer",
        "body": (
            "Platform and DevOps role owning AWS infrastructure, container operations, "
            "Terraform-based CI/CD, observability, security compliance, and incident "
            "response. Also includes ETL and data warehouse infrastructure operation, "
            "with collaboration on security-focused DevOps and MLOps environments."
        ),
    },
    "data_ml_platform_ops": {
        "title": "DevOps Engineer (Data/ML Platform)",
        "body": (
            "Data and ML platform operations role responsible for AWS architecture, "
            "Kubernetes-based production data and ML platforms, GitOps and CI/CD, "
            "Terraform automation, observability, and operational automation. "
            "Preferred experience includes Kafka, Kinesis, Spark, Flink, and "
            "large-scale data platform operations in a regulated environment."
        ),
    },
    "llm_rag_service": {
        "title": "AI Engineer",
        "body": (
            "Generative AI service role for enterprise products. Build LLM and RAG "
            "applications, agent workflows, inference services, model pipelines, "
            "vector retrieval, and cloud-operated AI services with Python and "
            "TypeScript. Improve quality, cost, security, and scalability of "
            "production AI features."
        ),
    },
    "feature_store_data_platform": {
        "title": "Data Engineer",
        "body": (
            "Data engineering role for analytics and AI collaboration. Design ETL "
            "and ELT pipelines, warehouse models, Airflow and dbt workflows, "
            "feature store delivery, BI-ready datasets, and data quality operations "
            "across a cloud-based data platform."
        ),
    },
    "data_infra_streaming_engineer": {
        "title": "Data Engineer",
        "body": (
            "Company-wide data infrastructure role designing and operating high-volume "
            "data architecture with Databricks and AWS. Build real-time and batch "
            "pipelines with Kafka, Spark Streaming, and Flink, operate data lake and "
            "warehouse systems, manage CDC flows, monitor data quality, and support "
            "reliable analytics and machine-learning data environments."
        ),
    },
    "ai_platform_operations": {
        "title": "AI Platform Engineer",
        "body": (
            "AI platform operations role focused on production service reliability. "
            "Own monitoring, logging, and performance management for AI services with "
            "Prometheus, Grafana, and tracing tools, optimize infrastructure and "
            "deployment workflows, and improve platform availability, latency, and "
            "operational resilience in cloud environments."
        ),
    },
    "ai_infrastructure_llmops": {
        "title": "AI Infrastructure Engineer",
        "body": (
            "AI infrastructure role for production AI products. Build llmops, "
            "model-serving infrastructure, inference pipelines, LLM evaluation, "
            "RAG retrieval, embeddings infrastructure, and deployment automation "
            "while also operating Kubernetes, Terraform, observability, and cloud "
            "reliability for AI services."
        ),
    },
    "data_platform_sre_observability": {
        "title": "Data Platform SRE",
        "body": (
            "Data platform SRE role operating warehouse workflows, Airflow runtime, "
            "Spark jobs, Kafka streaming, and data pipeline reliability while also "
            "owning Kubernetes, Terraform, observability, and incident response for "
            "analytics systems."
        ),
    },
    "analytics_infrastructure_experimentation": {
        "title": "Analytics Infrastructure Engineer",
        "body": (
            "Analytics infrastructure role building warehouse platforms, dbt models, "
            "Airflow orchestration, experimentation datasets, Spark processing, and "
            "data platform reliability tooling with Kubernetes and cloud operations."
        ),
    },
    "devops_data_platform_foundations": {
        "title": "DevOps Engineer (Data Platform Foundations)",
        "body": (
            "DevOps role for data platform foundations. Operate Kubernetes clusters, "
            "Terraform automation, observability, incident response, Airflow runtime, "
            "Spark and Kafka jobs, warehouse pipelines, and platform reliability for "
            "analytics products."
        ),
    },
    "devops_data_pipeline_reliability": {
        "title": "DevOps Engineer (Data Platform)",
        "body": (
            "DevOps role for data platform reliability. Build Kafka streaming, Spark "
            "pipelines, warehouse orchestration, dbt jobs, Airflow DAG operations, "
            "data quality runtime, and data platform reliability tooling for product "
            "analytics systems."
        ),
    },
    "mlops_inference_runtime": {
        "title": "MLOps Engineer",
        "body": (
            "MLOps role building model-serving runtime, inference pipelines, llmops "
            "tooling, evaluation workflows, embeddings infrastructure, RAG retrieval, "
            "and deployment automation for production AI services."
        ),
    },
    "frontend_next_typescript": {
        "title": "Frontend Engineer",
        "body": (
            "Frontend product role building customer-facing web experiences with "
            "Next.js, TypeScript, React, Storybook, Tailwind, and state-management "
            "libraries. Focus on design systems, user interaction quality, and fast "
            "iteration in a product team with API collaboration and release ownership."
        ),
    },
    "ios_native_mobile": {
        "title": "iOS Engineer",
        "body": (
            "Native mobile role building and operating iOS applications with Swift "
            "and SwiftUI. Own App Store delivery, user experience quality, app "
            "performance, security, release operations, and close collaboration with "
            "product and design teams."
        ),
    },
    "generative_ai_research_engineer": {
        "title": "Machine Learning Research Engineer",
        "body": (
            "Generative AI research role focused on model personalization, efficient "
            "fine-tuning, machine learning experimentation, model evaluation, "
            "training pipelines, and applied research for large-scale AI systems. "
            "Requires strong ML foundations and experience improving model quality "
            "and efficiency in production-oriented research environments."
        ),
    },
    "product_designer_design_system": {
        "title": "Product Designer",
        "body": (
            "Product design role shaping end-to-end user experience for a B2B SaaS "
            "platform. Own UX flows, UI patterns, design systems, experimentation "
            "hypotheses, product discovery, analytics-informed iteration, and close "
            "collaboration with product managers and engineers."
        ),
    },
    "qa_automation_platform_quality": {
        "title": "QA Automation Engineer",
        "body": (
            "Quality assurance role building automated regression coverage for web "
            "products and APIs. Own test planning, release validation, CI pipeline "
            "integration, flaky test reduction, and cross-team quality processes "
            "for a fast-moving product organization."
        ),
    },
    "embedded_firmware_iot": {
        "title": "Embedded Software Engineer",
        "body": (
            "Embedded software role developing firmware for connected devices with "
            "C and C++, RTOS scheduling, MCU integration, hardware interfaces, "
            "low-level debugging, and reliability validation for production IoT systems."
        ),
    },
    "game_client_unity_liveops": {
        "title": "Game Client Engineer",
        "body": (
            "Game client role building live game features with Unity, gameplay "
            "systems, rendering optimization, asset integration, client performance, "
            "and live operations support in collaboration with design and server teams."
        ),
    },
}
