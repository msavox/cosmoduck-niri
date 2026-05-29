# Building the stack from source

These scripts reproduce the jammy backport: they fetch each upstream project at
a pinned ref (`versions.env`), apply the niri patches (`patches/`), build, and
install into `/usr/local`. Ubuntu 22.04 ships none of this at a usable version,
which is the whole reason this repo exists.

```sh
./00-deps.sh        # toolchain + -dev packages (uses sudo, run once)
./build-all.sh      # build + install everything, in order
```

Then install the rice as your normal user: `../rice/setup.sh`.

Each step is standalone — run `./01-libwayland.sh`, `./08-niri.sh`, etc. on its
own. Override `WORKDIR` (checkout/build dir, default `~/.cache/cosmoduck-niri-build`)
or `PREFIX` (install prefix, default `/usr/local`) via the environment.

## What each step does

| Step | Component | Why it's built from source on jammy |
|------|-----------|-------------------------------------|
| 01 | libwayland-client 1.23.1 | jammy's 1.20 crashes Firefox under niri (`wl_pointer has no event 9`). Only the client lib is installed. |
| 02 | libdisplay-info 0.2.0 | niri runtime dependency, not packaged on jammy. Also builds `di-edid-decode`. |
| 03 | Xwayland 23.1.0 | jammy's Xwayland is too old for niri's protocols. Built against the staged newer wayland. |
| 04 | xwayland-satellite | rootless Xwayland integration for niri. |
| 05 | SwayNotificationCenter 0.9 | notifications + control center (GTK3). |
| 06 | nwg-dock | optional dock (the rice's default dock is waybar-based). |
| 07 | swaylock 1.8.5 | jammy's 1.5 is incompatible with niri (input-inhibitor). |
| 08 | niri (v26.04 + patches) | the compositor. Not packaged on jammy. |

## Honest status

- **Tested on the author's jammy box:** `01-libwayland` and `08-niri` mirror the
  exact scripts/patches used to build what's running here.
- **Reconstructed from build provenance:** `02`–`07` follow each project's
  standard build and the versions actually installed, but the scripts themselves
  haven't been re-run end-to-end on a clean machine. On a fresh box you may hit a
  missing `-dev` package — meson/cargo will name it; `apt install` it and re-run
  the step. `03-xwayland` is the fiddliest (it stages its own wayland).

If you just want a working desktop without compiling anything, install the
prebuilt package from [`../dist/`](../dist) instead — see the top-level README.
