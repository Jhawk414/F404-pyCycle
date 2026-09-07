[![CI](https://github.com/Jhawk414/F404-pyCycle/actions/workflows/pycycle_test_workflow.yml/badge.svg)](https://github.com/Jhawk414/F404-pyCycle/actions)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](meta/LICENSE.txt)

# F404-pyCycle

A GE F404 twin-spool, low-bypass, mixed-flow, afterburning turbofan **cycle
deck** — design-point sizing plus altitude/Mach/dTs off-design sweeps — built
on [NASA Glenn's pyCycle](https://github.com/OpenMDAO/pyCycle) and
[OpenMDAO](https://openmdao.org/).

Given a thrust target and a handful of component design choices (fan/HPC
pressure ratios, efficiencies, cooling bleed fractions), this repo sizes the
engine at sea-level-static conditions, then sweeps it across altitude,
ambient-temperature offset, and throttle to produce a converged off-design
performance map — the kind of tabular "cycle deck" a preliminary-design or
performance group would hand off to a vehicle-integration team.

**Status:** actively developed. Single-engine model with separate dry (mil
power) and wet (afterburning) DESIGN points; full alt/dTs/throttle sweep
infrastructure in place. See [Current status](#current-status) for
convergence coverage and [Roadmap](#roadmap) for what's next. Not yet
validated against public F404 performance data.

## Table of contents

- [Repo layout](#repo-layout)
- [Architecture and data flow](#architecture-and-data-flow)
- [Installation](#installation)
- [Usage](#usage)
- [Current status](#current-status)
- [Roadmap](#roadmap)
- [Acknowledgments](#acknowledgments)
- [License](#license)
