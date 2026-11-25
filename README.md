# Spotify Knowledge Graph

## Project description

This project develops an RDF knowledge graph based on the
[Almost a Million Spotify Tracks dataset](https://zenodo.org/records/11453410).

The objective is to transform the original tabular dataset into
a structured, interoperable and machine-readable RDF representation.

## Data model

The conceptual model includes the following classes:

- Track
- Artist
- Album
- Genre
- ChartEntry
- Market

The model reuses established vocabularies and ontologies,
including the Music Ontology, Dublin Core, FOAF and RDF Schema,
and introduces a custom vocabulary for Spotify-specific concepts.

## Project resources

- Ontology: [`ontology/spotify.ttl`](ontology/spotify.ttl)
- SHACL validation shapes: [`shacl/shapes.ttl`](shacl/shapes.ttl)
- RDF conversion pipeline: [`src/pipeline.py`](src/pipeline.py)

## Quickstart

```bash
pip install -r requirements.txt
python src/pipeline.py --input data/tracks.csv --output data/spotify_kg.nt
```

## Source dataset

Almost a Million Spotify Tracks.

Zenodo: https://zenodo.org/records/11453410

## License

Licensed under [CC BY 4.0](LICENSE).
