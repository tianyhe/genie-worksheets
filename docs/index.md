# Home

<p align="center">
    <h1 align="center">
        <img src="assets/genie_worksheets_circle.png" width=100px>
        <br>
        <b>GenieWorksheets</b>
        <br>
        <a href="https://arxiv.org/abs/2407.05674">
            <img src="https://img.shields.io/badge/cs.CL-2407.05674-b31b1b"
            alt="arXiv">
        </a>
        <a href="https://ws.genie.stanford.edu/">
            <img src="https://img.shields.io/badge/website-genie.stanford.edu-blue"
            alt="Website">
        </a>
        <a href="https://ws.genie.stanford.edu/docs/">
            <img src="https://img.shields.io/badge/docs-genie.stanford.edu-blue"
            alt="Docs">
        </a>
    </h1>
</p>
<p align="center">
    Framework for creating reliable conversational agents
</p>

Genie is a programmable framework for creating task-oriented conversational agents that are designed to handle complex user interactions and knowledge access.
Unlike LLMs, Genie provides reliable grounded responses, with controllable agent policies through its expressive specification, Genie Worksheet.
In contrast to dialog trees, it is resilient to diverse user queries, helpful with knowledge sources, and offers ease of programming policies through its declarative paradigm.

[Research Preprint](https://arxiv.org/abs/2407.05674): To be presented at ACL 2025

![Genie Worksheets Logo](assets/banner.jpg)

!!! tip "When to use Genie Worksheets?"
    GenieWorksheets excels at handling complex dialogues where the agent actively provides assistance to the user.
You should use GenieWorksheets if you need:

    - Task-oriented agents integrated with knowledge - GenieWorksheets uniquely combines both capabilities.
    
    - Mixed-initiative conversations where users can interrupt and switch between tasks seamlessly.
    
    - Precise control over agent responses and behaviors through explicit programming controls.

##  :rocket: Features

- **High-Level Declarative Specification:** Allows developers to easily define variables and actions for conversations through a spreadsheet-like format, without needing to manually code complex dialogue trees or manage LLM prompts.

- **Integrated Knowledge and Task Handling:** Uniquely combines the ability to handle both structured database queries and API calls in a single conversation flow, letting users seamlessly mix questions with task completion.

- **Reliable State Tracking:** Maintains conversation context through a formal dialogue state representation, reducing hallucinations and repetitive questioning common in pure LLM approaches.

- **Programmable Agent Policies:** Provides fine-grained control over agent behavior through explicit policy definitions, while still maintaining natural conversation flow and handling unexpected user inputs.

## :zap: Getting Started

- Install the package ([see installation for detailed instructions](installation.md))
- Define your agent in a python file
- Run your agent using the GenieWorksheets command-line interface or through a web interface

## :vs: Comparative Analysis


| Feature                  | Pure LLMs | Dialog Trees | GenieWorksheets |
|--------------------------|-----------|--------------|----------------|
| Handles unexpected queries | :white_check_mark: | :x: | :white_check_mark: |
| Reliable output        | :x:       | :white_check_mark: | :white_check_mark: |
| Knowledge integration    | :white_check_mark: | :x: | :white_check_mark: |
| Natural conversations    | :white_check_mark: | :x: | :white_check_mark: |
| Control over responses   | :x:       | :white_check_mark: | :white_check_mark: |
| Complex logic support    | :x:       | :white_check_mark: | :white_check_mark: |
| Low hallucination risk    | :x:       | :white_check_mark: | :white_check_mark: |
| Handles interruptions    | :white_check_mark: | :x: | :white_check_mark: |
| Programmable behaviors   | :x:       | :white_check_mark: | :white_check_mark: |
| Dynamic field dependencies | :x:       | :white_check_mark: | :white_check_mark: |
| Development speed        | :white_check_mark: | :x: | :white_check_mark: |


## :books: Research Paper

GenieWorksheets was introduced in our paper ["Coding Reliable LLM-based Integrated Task and Knowledge Agents with GenieWorksheets"](https://arxiv.org/abs/2407.05674). The paper details the design principles, implementation, and evaluation of the framework.

### Citation

If you use GenieWorksheets in your research, please cite our paper:

```bibtex
@article{genieworksheets,
  title={Coding Reliable LLM-based Integrated Task and Knowledge Agents with GenieWorksheets},
  author={Joshi, Harshit and Liu, Shicheng and Chen, James and Weigle, Robert and Lam, Monica S},
  journal={arXiv preprint arXiv:2407.05674},
  year={2024}
}
```

GenieWorksheets logo is designed with the help of DALL-E.