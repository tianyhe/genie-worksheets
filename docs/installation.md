# Installation

## 🛠️ Prerequisites

We recommend using [uv](https://github.com/astral-sh/uv) as the package installer for GenieWorksheets. UV is a fast, reliable Python package installer and resolver.

!!! tip "Why UV?"
    UV offers significantly faster installation times and more reliable dependency resolution compared to pip. It's especially helpful when working with complex Python projects.


## 📦 Installation Steps

1. First, install UV by following the [UV installation guide](https://github.com/astral-sh/uv?tab=readme-ov-file#installation)

2. Clone the GenieWorksheets repository: 

    ```bash
    git clone https://github.com/stanford-oval/genie-worksheets.git
    ```

3. Navigate to the project directory:

    ```bash
    cd genie-worksheets
    ```

4. Create and activate a virtual environment:

    ```bash
    uv venv
    source venv/bin/activate
    ```

5. Sync the dependencies:

    ```bash
    uv sync
    ```

## :question: Issues?

If you encounter any issues, please refer to the [Troubleshooting](troubleshooting.md) guide.

Or, if you're stuck, please [open an issue](https://github.com/stanford-oval/genie-worksheets/issues/new) and we'll do our best to help you out.