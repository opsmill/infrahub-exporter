<!-- markdownlint-disable -->
![Infrahub Logo](https://assets-global.website-files.com/657aff4a26dd8afbab24944b/657b0e0678f7fd35ce130776_Logo%20INFRAHUB.svg)
<!-- markdownlint-restore -->

# Infrahub Exporter

[Infrahub](https://github.com/opsmill/infrahub) by [OpsMill](https://opsmill.com) acts as a central hub to manage the data, templates and playbooks that powers your infrastructure. At its heart, Infrahub is built on 3 fundamental pillars:

- **A Flexible Schema**: A model of the infrastructure and the relation between the objects in the model, that's easily extensible.
- **Version Control**: Natively integrated into the graph database which opens up some new capabilities like branching, diffing, and merging data directly in the database.
- **Unified Storage**: By combining a graph database and git, Infrahub stores data and code needed to manage the infrastructure.

## Introduction

Infrahub Exporter is a service that exports metrics and service discovery information from Infrahub to monitoring systems like Prometheus and OpenTelemetry.

Infrahub Exporter acts as a bridge between your Infrahub instance and monitoring tools, providing:

1. **Metrics Export**: Collects and exposes metrics from Infrahub nodes for monitoring
2. **Service Discovery**: Provides dynamic service discovery for Prometheus based on Infrahub data
3. **OpenTelemetry Integration**: Supports sending metrics to OpenTelemetry collectors

## Using Infrahub exporter

Documentation for using Infrahub exporter is available [here](https://docs.infrahub.app/exporter/)
