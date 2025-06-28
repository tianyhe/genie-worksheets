from course_enroll import agent

from worksheets.core.context import GenieContext
from worksheets.utils.annotation import get_context_schema

local_context = GenieContext()
agent.runtime.execute(
    """
main = Main(student_info=StudentInfo(name='John Doe', student_id='1234567890'))""",
    local_context,
    sp=True,
)

print(local_context.context)

agent.runtime.execute(
    """answer = Answer('SELECT DISTINCT ON (unnest(c.breadth_requirement)) c.course_id, c.course_codes, c.title, unnest(c.breadth_requirement) AS breadth_category, r.average_rating, summary(r.reviews) AS reviews_summary FROM courses c JOIN ratings r ON c.course_id = r.course_id WHERE r.average_rating >= 4.0 ORDER BY unnest(c.breadth_requirement), r.average_rating DESC LIMIT 5', {}, ['c.course_codes', 'c.title', 'unnest', 'c.breadth_requirement', 'r.average_rating', 'summary', 'r.reviews', 'courses', 'ratings'], 'What courses should I take?')""",
    local_context,
    sp=True,
)

print(local_context.context)

print(get_context_schema(local_context))
