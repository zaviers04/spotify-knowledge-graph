
# Spotify Knowledge Graph

Documentation for the Spotify Knowledge Graph project.

## Overview

An RDF representation of the Almost a Million Spotify Tracks dataset.

## Ontology

The project uses existing music and metadata vocabularies,
complemented by a custom Spotify vocabulary.

## Validation

A machine-checkable SHACL profile in [`shacl/shapes.ttl`](../shacl/shapes.ttl) defines the structural and datatype constraints of the RDF representation, enforced automatically by [`src/pipeline.py`](../src/pipeline.py).

## Source

[Almost a Million Spotify Tracks](https://zenodo.org/records/11453410)
