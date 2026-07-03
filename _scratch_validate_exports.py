"""Throwaway probe: raw .conv export text for variations 0 and 2."""
import pyEPR_pyaedt as epr

pinfo = epr.ProjectInfo(
    project_path=r"C:\Code\pyEPR_pyaedt\_example_files",
    project_name="pyEPR_tutorial1",
    design_name="1. single_transmon",
)
eprh = epr.DistributedAnalysis(pinfo)

for variation in ["0", "2"]:
    vs = eprh.get_variation_string(variation)
    print(f"\n===== variation {variation}: {vs} =====")
    df, text = pinfo.setup.get_convergence(vs)
    print("RAW TEXT >>>")
    print(text)
    print("<<< END RAW")

pinfo.disconnect()
print("PROBE DONE")
