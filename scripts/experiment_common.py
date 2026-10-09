"""Public names for the deliberately bounded Phase G catalog methods."""
METHODS = ("scenario_matrix", "full_factorial", "monte_carlo_catalog")
OPERATIONS = tuple("experiment.sample_plan." + method for method in METHODS)
