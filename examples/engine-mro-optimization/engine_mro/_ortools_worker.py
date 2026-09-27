"""Solve an MPS file with an OR-Tools backend and print the solution as JSON.

Runs in its own process: OR-Tools and highspy bundle conflicting HiGHS
symbols, so they cannot be loaded into the same interpreter.
"""

import json
import sys

from ortools.linear_solver.python import model_builder as mb


def main() -> None:
    path, name, time_limit, params, msg = sys.argv[1:6]
    model = mb.Model()
    model.import_from_mps_file(path)
    solver = mb.Solver(name)
    solver.set_time_limit_in_seconds(float(time_limit))
    solver.set_solver_specific_parameters(params)
    solver.enable_output(msg == "1")
    result = solver.solve(model)
    out = {"status": result.name, "values": None, "bound": None}
    if result in (mb.SolveStatus.OPTIMAL, mb.SolveStatus.FEASIBLE):
        out["values"] = {v.name: solver.value(v) for v in model.get_variables()}
        out["bound"] = solver.best_objective_bound
    json.dump(out, sys.stdout)


if __name__ == "__main__":
    main()
