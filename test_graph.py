import pandas as pd
from rdflib import Graph, Namespace, RDF

df = pd.read_csv("data/tracks.csv")

g = Graph()
g.parse("data/test.nt", format="nt")

MO = Namespace("http://purl.org/ontology/mo/")

source_tracks = df["track_id"].nunique()
generated_tracks = len(set(g.subjects(RDF.type, MO.Track)))

print("Unique source tracks:", source_tracks)
print("Generated RDF tracks:", generated_tracks)
print("Difference:", source_tracks - generated_tracks)