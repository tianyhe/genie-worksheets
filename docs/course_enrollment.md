---
title: Course Enrollment Assistant
description: Guide for building a course enrollment assistant using Genie Worksheets
---

# Course Enrollment Assistant

!!! note "Overview"
    The Course Enrollment Assistant is a sophisticated dialogue agent that helps students with course selection and enrollment. It demonstrates how to build a complex task-oriented agent that integrates multiple data sources and handles nested workflows.

## Knowledge Base

The system uses four main tables:

### 1. Courses Table
Contains course information including:

- Basic details (ID, title, units)
- Requirements (general, foundations, breadth)
- Prerequisites
- Course descriptions

### 2. Offerings Table
Contains course scheduling information:

- Days and times
- Instructors
- Seasons (quarters)

### 3. Ratings Table
Contains course feedback:

- Student ratings and reviews
- Historical data by term
- Instructor performance

### 4. Programs Table
Contains degree program information:

- Program levels (BS, MS, PhD)
- Specializations
- Requirements

## Implementation Guide

### Knowledge Base Setup

```python
suql_knowledge = SUQLKnowledgeBase(
    tables_with_primary_keys={
        "courses": "course_id",
        "ratings": "rating_id",
        "offerings": "course_id",
        "programs": "program_id",
    },
    database_name="course_assistant"
)
```

### API Functions

The system includes three main API functions:

```python
def course_detail_to_individual_params(course_detail)
def courses_to_take_oval(**kwargs)
def is_course_full(course_id, **kwargs)
```

### Worksheet Structure

The course enrollment worksheet typically includes:

```yaml
# Main Course Search Worksheet
WS Name: CourseSearch
WS Kind: Task
Fields:
  - Name: search_query
    Kind: input
    Type: string
    Required: true
    Description: "What kind of course are you looking for?"

# Course Enrollment Worksheet
WS Name: CourseEnroll
WS Kind: Task
Fields:
  - Name: course_id
    Kind: input
    Type: int
    Required: true
    Description: "Course ID to enroll in"
    
  - Name: confirm_enrollment
    Kind: input
    Type: boolean
    Required: true
    Description: "Confirm enrollment in the course"
```

## Usage Guide

### Common Use Cases

!!! example "Course Search"
    - Students can search for courses using natural language queries
    - Example: "Find me programming courses" or "Show me AI courses with good ratings"
    - The system uses SUQL to query across structured and unstructured data

!!! example "Course Information"
    - Students can ask about course details, prerequisites, and requirements
    - Example: "What are the prerequisites for CS229?"
    - Combines data from multiple tables to provide comprehensive information

!!! example "Course Enrollment"
    - Students can enroll in courses after confirming details
    - System checks course availability using `is_course_full`
    - Requires confirmation before finalizing enrollment

### Best Practices

!!! tip "Knowledge Integration"
    - Use the SUQL knowledge base for hybrid queries across structured and unstructured data
    - Leverage the React parser for complex query understanding

!!! tip "Workflow Management"
    - Handle nested workflows (search → details → enrollment)
    - Always confirm important actions before execution
    - Maintain context across the conversation

!!! warning "Error Handling"
    - Check course availability before enrollment
    - Validate prerequisites
    - Handle cases where courses are full or unavailable

### Example Conversation Flow

```
User: "Find me programming courses"
Agent: [Queries courses table with programming-related filters]
      [Returns list of courses]

User: "Tell me more about CS106B"
Agent: [Queries multiple tables for comprehensive information]
      [Returns course details, ratings, and current offerings]

User: "I'd like to enroll in this course"
Agent: [Checks prerequisites and availability]
      [Asks for confirmation]
      [Processes enrollment if confirmed]
```

!!! success "Summary"
    This guide provides a foundation for understanding how the Course Enrollment Assistant is structured using Genie Worksheets. The system demonstrates the power of combining structured data queries, natural language understanding, and workflow management in a single conversational agent.
