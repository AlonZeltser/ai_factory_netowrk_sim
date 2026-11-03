# Ring Collective Stall Visualizer

The Ring Collective Stall Visualizer is an interactive dashboard for exploring ring-collective log output from a completed simulation run.

It is intended to help answer operational questions such as:
- Which chains progressed smoothly, and which stalled?
- Where in time did stalls appear?
- Which hops were most expensive or congested?
- How do two runs compare visually?

This document focuses on how to use the tool and what each view means.

---

## What the visualizer shows

The visualizer supports three viewing modes:

- **Gantt** — timeline view of ring-chain activity over simulation time
- **Heatmap** — hop-by-hop metric view across chains
- **Both** — shows both views together for the same filtered data

You can use it with:
- **one log file** for normal inspection
- **two log files** for side-by-side Gantt comparison

---

## Input

The visualizer expects a ring collective log file produced by a completed test run.

Typical usage:
- open a log from your run output
- narrow the data using filters such as job, step, phase, bucket, or operation
- inspect the timeline and/or heatmap

Supported upload types in the UI:
- `.log`
- `.txt`

---

## Starting the visualizer

From the repository root:

```powershell
cd C:\Users\alonz\repos\studies\seminar\seminar_wt_1\seminar_in_networks\ring_collective_stall_visualizer
pip install -r requirements.txt
python -m streamlit run app.py
```

After startup, Streamlit opens the dashboard in your browser.

---

## Basic workflow

1. Start the app
2. Upload a ring log file
3. Choose the desired view: **Gantt**, **Heatmap**, or **Both**
4. Filter the dataset if needed
5. Adjust chain display count
6. Inspect the graph interactively
7. Use the PNG/PDF download buttons under each chart when you want an export

If a second log is uploaded, you can visually compare two runs in Gantt mode.

---

## Sidebar controls

### 1) Upload ring log
Upload the primary ring log file.

This is required before anything can be visualized.

### 2) Upload second ring log for comparison
Optional.

If provided, the dashboard can compare two runs in the Gantt view.

### 3) Filters
Depending on the parsed log contents, the sidebar may allow filtering by:
- `job`
- `step`
- `phase`
- `bucket`
- `op`

These filters apply to the currently loaded dataset before plotting.

### 4) Max chains to display
Limits how many chains are drawn.

This is useful when the log contains many chains and you want a more readable view.

### 5) View
Controls whether the dashboard shows:
- **Gantt**
- **Heatmap**
- **Both**

This is the control used to show or hide the heatmap.

### 6) PNG / PDF export
After each rendered chart, the UI provides download buttons:
- **Download Gantt as PNG**
- **Download Gantt as PDF**
- **Download Heatmap as PNG**
- **Download Heatmap as PDF**

The exported filename includes a timestamp so repeated exports do not overwrite each other.

---

## Direct PDF export script (without Streamlit)

If you want deterministic, scriptable PDF generation (for reports/CI), use:

`ring_collective_stall_visualizer/export_gantt_pdf.py`

This script reads one to four ring logs, applies optional filters, builds the same Gantt chart, and writes a presentation-sized PDF directly.

Example from repository root:

```powershell
python ring_collective_stall_visualizer\export_gantt_pdf.py `
  results\_tmp_ringviz_pdf_script_test\scan_1.log `
  results\_tmp_ringviz_pdf_script_test\scan_2.log `
  results\_tmp_ringviz_pdf_script_test\scan_3.log `
  results\_tmp_ringviz_pdf_script_test\scan_4.log `
  --labels "Scan 1,Scan 2,Scan 3,Scan 4" `
  --color-by stalled_packets `
  --chain-limit 16 `
  --out results\_tmp_ringviz_pdf_script_test\gantt_stalled_packets.pdf
```

Required options:
- `--out FILE` output PDF path
- `--color-by` one of: `stall_bucket`, `stalled_packets`, `duration_ms`, `max_egress`, `avg_egress`
- `--chain-limit N` max number of chains to draw

Optional:
- `--labels "A,B,..."` panel names in multi-log mode (unlabeled panels are named `Scan N`)
- `--filter key=v1,v2,...` repeatable (for example `--filter step=0 --filter phase=1`); a key the log doesn't have is an error

---

## Gantt view

### Purpose
The Gantt view helps you understand **when** each chain/hop was active and where delays appeared over time.

### What it shows
- **X-axis**: simulation time
- **Y-axis**: chain start host
- **Bars**: activity windows for individual chain hops / transfers
- **Color**: selected metric

### Color options
The dashboard lets you color the Gantt chart by one of the available metrics, such as:
- stall bucket
- stalled packets
- duration
- max egress
- average egress

### When to use it
Use the Gantt view when you want to:
- identify where a run slowed down
- see timing spread across chains
- compare the pacing of two runs
- visually inspect stall patterns over time

---

## Heatmap view

### Purpose
The heatmap helps you understand **where** in the ring path the cost or pressure is concentrated.

### What it shows
- **X-axis**: hop index in the chain
- **Y-axis**: chain start host
- **Cell color**: selected metric value

### Heatmap metrics
The heatmap can display one of the available metrics, such as:
- duration
- stalled packets
- max egress
- average egress
- egress sum

### When to use it
Use the heatmap when you want to:
- find expensive hops
- spot repeated bottlenecks across chains
- compare hop-level pressure patterns
- inspect where stalls cluster structurally rather than temporally

---

## Heatmap enable / disable

The heatmap is controlled by the **View** selector.

- To **show** the heatmap, choose **Heatmap** or **Both**
- To **hide** the heatmap, choose **Gantt**

### Is heatmap control per job?
No.

Heatmap visibility is **global for the current filtered selection**, not per job.

That means:
- if you filter to one job, the heatmap shows that job
- if you filter to several jobs, the heatmap reflects all currently selected rows together
- you cannot enable the heatmap for one job and disable it for another inside the same session view

For the clearest analysis, it is usually best to filter down to a single job, and often also a single step.

---

## Comparing two runs

If you upload a second log file, the visualizer can compare two runs in the Gantt view.

This is useful for questions like:
- did a change reduce stalls?
- did the timeline compress or stretch?
- did chain progression become more balanced?

In comparison mode:
- the two runs are shown in separate aligned panels
- each run can be labeled in the sidebar
- the comparison is most useful when both logs represent comparable workloads / steps

---

## Data preview and run summary

The dashboard also provides:
- a **run summary** with high-level counts and totals
- a **parsed data preview** table for inspecting the filtered records directly

These sections are useful for verifying that:
- the right file was uploaded
- the expected job/step was selected
- the data remaining after filtering is what you intended to analyze

---

## Recommended usage patterns

### For timeline inspection
Use:
- **View = Gantt**
- filter to one job / one step if possible
- color by stall-related or duration-related metrics

### For structural bottleneck inspection
Use:
- **View = Heatmap**
- filter to one job / one step if possible
- switch metrics to compare duration vs stall vs egress pressure

### For combined analysis
Use:
- **View = Both**

This is useful when you want to correlate:
- **when** something happened (Gantt)
- **where** it happened in the ring (Heatmap)

### For before/after comparison
Use:
- primary log + comparison log
- **View = Gantt** or **Both**
- the same filters on comparable runs

---

## Troubleshooting

### No data appears after upload
Possible causes:
- the file is not a ring collective log in the expected format
- the selected filters removed all rows

Try:
- uploading a different run log
- clearing or widening filters

### "No rows left after filtering"
The current filter combination removed all matching rows.

Try selecting fewer filters or restoring all values.

### Heatmap looks too busy
Try:
- reducing the number of displayed chains
- filtering to a single job
- filtering to a single step, phase, bucket, or operation

### Comparison is hard to interpret
Try:
- comparing runs from the same workload and step
- using the same filter selections for both
- narrowing the dataset before comparison

---

## Practical interpretation tips

- **Large time spread in Gantt** usually suggests imbalance or stalls over time
- **Hot columns in Heatmap** can indicate expensive hops shared across chains
- **Many non-zero stall colors** often point to congestion or queue pressure
- **Cleaner, tighter Gantt bars** often indicate a more efficient run

---

## Quick start summary

```powershell
cd C:\Users\alonz\repos\studies\seminar\seminar_wt_1\seminar_in_networks\ring_collective_stall_visualizer
pip install -r requirements.txt
python -m streamlit run app.py
```

Then:
1. upload a ring log
2. choose **Gantt**, **Heatmap**, or **Both**
3. filter by job / step / phase / bucket / op if needed
4. inspect the resulting visualization

