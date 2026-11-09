# Team workflow

1. Open an issue with an owner and observable completion criteria.
2. Update main (`git switch main`, `git pull --ff-only`) and create a task branch
   (`git switch -c feature/short-task`).
3. Keep changes focused. Coordinate edits to `include/pins.h`; document wiring
   changes in the same pull request. Never assume a Feather V2 pin label matches
   the original HUZZAH32.
4. Compile the affected environment. For shared changes compile all of them:
   `pio run -e dispenser -e dispenser-wokwi -e beam-break -e load-cell -e ui-panel -e motor-drv8833 -e motor-tb6612`
   and run the host tests: `pio test -e native`.
5. Commit and push your branch; open a pull request. State which checks compiled
   and which actually ran on hardware. Include serial observations where useful.
6. Ask a teammate to review. Merge after review and relevant bench checks, then
   update local main. Tag demonstrated versions with their hardware/test record.

Do not commit credentials or generated `.pio` files. Avoid unrelated formatting
changes. Repository admins should enable PR review and passing build requirements
on main where the GitHub plan permits; this setup does not change those settings.
