# AI Exam Grader

[![License: Non-Commercial](https://img.shields.io/badge/License-Non--Commercial-orange.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

English | [简体中文](README_CN.md)

---

AI Exam Grader grades handwritten answer sheets with a vision model from OpenAI (or a compatible API) or Google Gemini. It reads each student's details, scores the answers against your rubric, and writes a report for every sheet plus a grade summary. After you review the results, the sheets are renamed after their students.

> [!IMPORTANT]
> **License Notice**
>
> This project is licensed under the **[NCEL-Strict License (Version 2.0)](./LICENSE)**.
> This is a **Source Available** but **Strictly Limited** non-commercial license.
>
> 🚫 **Commercial Use Strictly Prohibited**: Includes sale, subscription, sponsorship, **Internal Use**, SaaS services, and AI model training.  
> 🚫 **Distribution of Modified Versions Prohibited**: You may **NOT** directly distribute modified source code or binaries (only Patch/Diff files are allowed).  
> 🚫 **Fork Restriction**: Public Forks are allowed ONLY for submitting PRs and must be deleted within 14 days after the PR is closed.  
> ✅ **Non-Commercial Only**: Personal study, academic research, and non-commercial use must retain the full copyright notice and license file.
>
> 💼 **Commercial License**:
> For commercial use or custom development, please contact the author for licensing: [nicofiela@outlook.com](mailto:nicofiela@outlook.com)

## ✨ Features

- **Automatic grading**: objective questions are checked against the answer key. Subjective questions are scored part by part following the rubric, with the points earned and missed. Sheets are graded in parallel, and an interrupted run picks up where it stopped.
- **Rubrics**: TXT, Markdown or PDF. A PDF is transcribed to Markdown page by page. The model extracts the answer key and the sheet layout, and grading starts only after you confirm them.
- **Student matching**: each sheet is matched to your roster in this order: a "Room-Seat" file name, the filled or written exam number, the written room and seat, then the handwritten class and name. Exams without exam numbers work too.
  - Class labels written differently, such as 701, 7(1)班, 七年级一班 and 初一1班, count as the same class.
  - A name that is one character off is still matched, but flagged for checking.
  - When a sheet is unclear, no student is picked; candidates are listed instead.
- **Review**: check each sheet's student, objective answers and subjective scores, with or without the scan beside them. Search by name, exam number or Room-Seat. Every change is logged.
- **Sheets named after students**: when review is finished, each graded sheet is renamed "Class-Name.jpg" (e.g. `701-张三.jpg`). Repeated names get a suffix, and sheets whose student is not yet confirmed, or marked No Name, keep their names. The scans stay in the original files backup.
- **Scores written on the sheets**: after grading and review, every graded sheet in `success/` gets its scores as small red tables, each "question | score" (e.g. `26(1) | 4分`, `MC | 57 pts`, `Total | 65`). The positions are set once per exam; on a shifted scan the tables move a little, but each names its question, so none is misread. The scores are redrawn when review changes them, always from the scan in `original_files/`, which is never changed.
- **Safe data**: scans are backed up before grading. Each sheet keeps its own report, so rescanned sheets and repeated file names never overwrite each other. Chinese and English interface.

> [!NOTE]
> Results depend on the model's image recognition and reasoning. A strong vision model is recommended.

## 🚀 Install and Run

Requires Python 3.10 or later, on macOS, Windows or Linux. Check with `python3 --version` (on Windows, `python --version`): the `python3` that comes with macOS may be older than 3.10, in which case install a newer one from [python.org](https://www.python.org/downloads/).

Install the dependencies in a virtual environment, `.venv` in the project folder, so they stay apart from the system Python. On macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Then start the app in the same terminal:

```bash
python AutoGrader.py
```

In a new terminal, activate the environment again before running (the `activate` line above); a `ModuleNotFoundError` on start usually means it is not activated. On macOS / Linux, `./run.sh` starts the app with `.venv` without activating it.

In the left panel, enter your API key, the provider (OpenAI / Gemini), the model name and, if needed, a base URL. Alternatively, copy `config_example.json` to `config.json` and fill it in; see [README_CONFIG.md](README_CONFIG.md).

To build an app: run `python build.py` on macOS or `python build_windows.py` on Windows. The result is in `dist/`.

## 🛠️ Workflow

1. **Prepare**
   - Rubric: `.txt`, `.md` or `.pdf`.
   - Answer sheets: scans in `.jpg` or `.png`, all in one folder. The scanner's file names are fine.
   - Student roster: optional but recommended. Excel or CSV with a header row, which can contain name, class, exam number (or student ID), room and seat columns. Chinese headers such as 姓名, 班级, 考号, 考场 and 座号 also work.
2. **Select files**: in the Resources area, choose the rubric, the answer-sheet folder and the roster.
3. **Grade**: click "Start Grading".
   - On the first run, the answer key and the sheet layout are extracted for you to confirm, then you place the scores (see step 6; you may skip for now or turn it off for the exam) before grading starts.
   - If you stop and start again, only unfinished sheets are graded; failed sheets are retried automatically.
   - When grading ends, the log summarizes the matching: how many sheets match the roster, how many need checking, and how many roster students have no sheet. A student on several sheets (e.g. a sheet scanned twice), a report whose sheet is missing, or counts that disagree are listed one by one, and the log ends with the number of issues to handle instead of "Finished!".
4. **Review**: click "Review" and go through each sheet's student, objective and subjective steps, then click "Confirm & Next". Confirming a sheet without a student opens a prompt. Close (the default) lets you choose the student; confirm again to go on. If the sheet has no name on it, choose No Name instead: the sheet is confirmed, the next one opens, and the grade summary's match method reads "No name on sheet".
   - Sheets are shown in the order they were scanned, as the paper pile is; a sheet renamed after its exam number or student stays in its place.
   - Sheets that need checking show what was recognized, and the candidate students appear first in the dropdown. A student you choose is recorded as "Chosen in review".
   - If the student is on other sheets too, the student panel names them with their scores and review status: the sheet may have been scanned twice. On the extra one, click "Remove This Sheet": its image and report move to `removed/` and leave the grade summary, while the scan stays in `original_files/`. Do not delete sheets in Finder, which leaves their reports behind and the counts off.
   - Use "Regrade" to grade a single sheet again. After changing the answer key, use "Regrade Obj." in the main window to recalculate all sheets.
5. **Renaming**: once every sheet is reviewed (passing the last sheet while some are skipped or not reviewed yet tells you how many are left and opens the first of them), the graded sheets are renamed "Class-Name" where they are (in `success/`), and their reports and the grade summary record the new names. A scan missing from `original_files/` is backed up first. If grading is still running, renaming waits until you finish reviewing after it.
6. **Scores on the sheets**: place the scores once in the Score Marks window and every sheet of the exam is marked at those positions (it opens before the first grading, or from "Score Marks" in the main window).
   - Pick an item on the right (total, multiple-choice total, each sub-question) and click on the sample to place it; drag a red score to move it. "Locate" asks the model once for positions on the current sample; it fills only the items not placed yet, and you check each one.
   - **Look at several samples with Previous/Next**: scans of one exam are often tens to a hundred pixels apart (cropped differently, two pages stitched). Put the tables in blank space outside the answer areas (e.g. in the margin outside the frame) and shifts rarely bring them over answers. The window warns about tables over dark writing, tables that overlap and tables at the image's edge; those are moved inside the image.
   - Every sheet gets its scores: scans cropped or proportioned unlike the sample are marked as usual, and a turned one too, with a note in the log. Before any report exists, the question list is guessed from the answer key and checked against the first report; scores are written once they match. After that, a sub-question missing from a report shows "—", and extra sub-questions or a total that differs from the sum of its questions are listed in the log ("Scores written ...; check its grades"); the total shown is the one the report records.
   - The scores are redrawn after grading, after confirming in review, after Regrade and after Regrade Obj.; the review window shows the new image.
   - Pause stops writing scores from then on and keeps those written; "Restore Scans (Remove Scores)" puts the scans back on the sheets this feature marked, keeping their names, scores and review history. An image changed in another program is neither overwritten nor restored.
   - Regrading and grading again use only the scans in `original_files/`, so no image with scores reaches the model, and no image with scores is ever backed up as a scan.

**File name tips**

- Sheets already sorted by seat can be named `Room-Seat` (e.g. `01-05.jpg`); that name is used first to find the student.
- To mark an absent student, add 缺 to the file name (e.g. `01-05缺.jpg`, `IMG_0003缺.jpg`). Sheets scoring zero are also marked absent.

## 📂 Output

Everything is written inside the answer-sheet folder. The Chinese interface uses Chinese folder names (阅卷数据, 阅卷报告, 原始文件, 成功归档, 失败归档).

```
answer-sheet folder/
├─ grading_data/     answer key, sheet layout, score positions (score_marks.json), PDF transcription and Grade_Summary.csv
├─ reports/          one .md report and one .json file per sheet
├─ original_files/   backup of the scans under their scanned names, taken before grading (never marked)
├─ success/          graded sheets, with their scores in red once score positions are set; renamed Class-Name after review (until then, a sheet not named Room-Seat is renamed to its exam number when one is read)
├─ failed/           sheets that failed, retried on the next run
└─ removed/          sheets taken out of the grades in review (e.g. scanned twice): one dated folder each, image and report kept where they were, so moving them back restores them
```

The grade summary lists each student's details, total score, scores for each objective and subjective question, the student details read from the sheet, the information check, the match method, the review status and the absence mark.

## 📄 License

This project is licensed under the **NCEL-Strict License (Version 2.0)**; see [LICENSE](LICENSE). For commercial use, please contact the author: nicofiela@outlook.com

Contributions are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md).
