"""Top picks: the few roles worth leaving a job for, judged by the person's assistant.

The engine does everything code can decide: it keeps who the person is
(`background`) and what they want (`brief`), narrows the Board's open roles to
the ones worth a judgment (`queue`, with the checkable hard rules of `rules`),
records each run of the judge (`runs`) and its verdicts (`verdicts`), and says
how setup and the routine stand (`setup`, `health`). The judgment itself is the
assistant's, made outside the engine and written back through
`tracker/agents/operations/picks.py`.
"""
