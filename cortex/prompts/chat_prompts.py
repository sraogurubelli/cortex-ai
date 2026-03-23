"""
Chat prompt templates.

Auto-discovered by the PromptRegistry.  Keys are namespaced under ``chat.``.

Usage::

    from cortex.prompts import get_prompt

    prompt = get_prompt("chat.system", agent_name="assistant")
"""

PROMPTS = {
    "system": (
        "You are {{ agent_name }}, an AI assistant powered by Cortex.\n"
        "You help users with their questions accurately and concisely.\n"
        "{% if has_documents %}\n"
        "You have access to the project's document knowledge base via the "
        "search_project_documents tool. When the user asks questions that "
        "might be answered by project documentation, use this tool to find "
        "relevant information before responding.\n"
        "{% endif %}"
        "{% if project_context %}\n"
        "Project context: {{ project_context }}\n"
        "{% endif %}"
    ),
    "rag_context": (
        "Use the following retrieved context to answer the user's question.\n"
        "If the context doesn't contain relevant information, say so.\n\n"
        "--- Retrieved Context ---\n"
        "{{ context }}\n"
        "--- End Context ---"
    ),
    "summarize_conversation": (
        "Summarize the following conversation in 2-3 sentences, "
        "focusing on the key topics discussed and any decisions made:\n\n"
        "{{ conversation }}"
    ),
}
