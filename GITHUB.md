# GitHub handoff

This folder is a self-contained Phase 2 package. It includes the Phase 1 corpus as supplied, the SQLite database, reproducible extraction and evaluation code, checked logs, and presentation notes. In the course GitHub repository, the package can reuse the existing `Phase 1` folder through `phase2/source_paths.py`.

Repository: `yababa-s/agriculture-assignment`, the repository referenced in the project brief. The review branch is `phase2-rebuild`; it keeps `main` unchanged.

If reproducing the branch from this local checkout:

```powershell
git remote add origin https://github.com/yababa-s/agriculture-assignment.git
git push -u origin phase2-rebuild
```

The commit should contain only this `Phase2_Submission` folder's contents. Review the branch in GitHub and open a pull request if the course repository should retain its existing structure.
