"""Answer policy with anti-hallucination contract for RAG responses."""

import logging
from typing import Literal, Optional

import google.generativeai as genai
from pydantic import BaseModel

from app.models.domain import StoredMessage
from app.rag.retrieval import RetrievalResult

logger = logging.getLogger(__name__)


class AnswerResult(BaseModel):
    """Result of answer generation."""

    answer: str
    found_status: Literal["FOUND", "NOT_FOUND", "ESCALATION"]
    sources: list[str]
    is_escalation: bool = False


class AnswerPolicy:
    """Policy for generating answers with anti-hallucination contract.
    
    Key principles:
    1. Never fabricate information about price, specs, availability
    2. Only use information from File Search citations
    3. Use fallback message when no relevant results found
    4. Handle escalation requests to human manager
    """

    FALLBACK_MESSAGE = (
        "🤖: в моей базе нет нужной информации по твоему вопросу, "
        "можешь задать уточнение или мне вызвать менеджера?"
    )

    ESCALATION_KEYWORDS = [
        "вызови менеджера",
        "позови менеджера", 
        "позови человека",
        "оператор"
    ]

    ESCALATION_RESPONSE = (
        "Понял, сейчас подключу менеджера. "
        "Он свяжется с вами в ближайшее время."
    )

    SYSTEM_PROMPT = """Ты — вежливый помощник продавца на Avito. 
Отвечай на вопросы покупателей ТОЛЬКО на основе предоставленной информации из базы знаний.

ВАЖНЫЕ ПРАВИЛА:
1. Используй ТОЛЬКО информацию из предоставленных фрагментов базы знаний
2. НЕ выдумывай цены, характеристики, наличие или условия
3. Если информации недостаточно для ответа — так и скажи
4. Отвечай кратко и по делу
5. Будь дружелюбным и профессиональным

Контекст диалога (последние сообщения):
{context}

Информация из базы знаний:
{knowledge}

Вопрос покупателя: {question}

Ответ:"""

    def __init__(self, api_key: str, model_name: str = "gemini-1.5-flash"):
        """Initialize answer policy.
        
        Args:
            api_key: Google Gemini API key
            model_name: Name of the Gemini model to use
        """
        self.api_key = api_key
        self.model_name = model_name
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)

    def needs_escalation(self, message: str) -> bool:
        """Check if message contains escalation keywords.
        
        Args:
            message: The customer message to check
            
        Returns:
            True if escalation is requested, False otherwise.
        """
        message_lower = message.lower()
        for keyword in self.ESCALATION_KEYWORDS:
            if keyword in message_lower:
                logger.info(f"Escalation keyword detected: '{keyword}'")
                return True
        return False

    def _format_context(self, messages: list[StoredMessage]) -> str:
        """Format chat history for the prompt.
        
        Args:
            messages: List of stored messages from chat history
            
        Returns:
            Formatted string with conversation context.
        """
        if not messages:
            return "Нет предыдущих сообщений."

        lines = []
        for msg in messages[-10:]:  # Last 10 messages for context
            sender = "Бот" if msg.is_bot_message else "Покупатель"
            text = msg.text or "[без текста]"
            lines.append(f"{sender}: {text}")

        return "\n".join(lines)

    def _format_knowledge(self, retrieval_result: RetrievalResult) -> str:
        """Format retrieved chunks for the prompt.
        
        Args:
            retrieval_result: Result from cascading retrieval
            
        Returns:
            Formatted string with knowledge base information.
        """
        if not retrieval_result.found or not retrieval_result.chunks:
            return "Релевантная информация не найдена."

        lines = []
        for i, chunk in enumerate(retrieval_result.chunks, 1):
            source = chunk.source_file
            text = chunk.text[:500]  # Limit chunk size
            lines.append(f"[{i}] Источник: {source}\n{text}")

        return "\n\n".join(lines)

    def _extract_sources(self, retrieval_result: RetrievalResult) -> list[str]:
        """Extract unique source file names from retrieval result.
        
        Args:
            retrieval_result: Result from cascading retrieval
            
        Returns:
            List of unique source file names.
        """
        sources = set()
        for chunk in retrieval_result.chunks:
            if chunk.source_file and chunk.source_file != "unknown":
                sources.add(chunk.source_file)
        return list(sources)

    async def generate_answer(
        self,
        question: str,
        context: list[StoredMessage],
        retrieval_result: RetrievalResult
    ) -> AnswerResult:
        """Generate answer based on RAG results with anti-hallucination contract.
        
        Args:
            question: The customer's question
            context: Chat history for context
            retrieval_result: Result from cascading retrieval
            
        Returns:
            AnswerResult with answer, status, and sources.
        """
        # Check for escalation first
        if self.needs_escalation(question):
            logger.info("Escalation requested, returning escalation response")
            return AnswerResult(
                answer=self.ESCALATION_RESPONSE,
                found_status="ESCALATION",
                sources=[],
                is_escalation=True
            )

        # Anti-hallucination: if no results, return fallback
        if not retrieval_result.found or not retrieval_result.chunks:
            logger.info("No RAG results, returning fallback message")
            return AnswerResult(
                answer=self.FALLBACK_MESSAGE,
                found_status="NOT_FOUND",
                sources=[],
                is_escalation=False
            )

        # Generate answer using Gemini with grounded context
        try:
            prompt = self.SYSTEM_PROMPT.format(
                context=self._format_context(context),
                knowledge=self._format_knowledge(retrieval_result),
                question=question
            )

            response = await self.model.generate_content_async(
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=0.3,  # Lower temperature for factual responses
                    max_output_tokens=500
                )
            )

            answer = response.text.strip() if response.text else self.FALLBACK_MESSAGE
            sources = self._extract_sources(retrieval_result)

            # Validate answer is not empty
            if not answer:
                logger.warning("Empty answer generated, using fallback")
                return AnswerResult(
                    answer=self.FALLBACK_MESSAGE,
                    found_status="NOT_FOUND",
                    sources=[],
                    is_escalation=False
                )

            logger.info(
                f"Generated answer with {len(sources)} sources, "
                f"strategy={retrieval_result.search_strategy}"
            )

            return AnswerResult(
                answer=answer,
                found_status="FOUND",
                sources=sources,
                is_escalation=False
            )

        except Exception as e:
            logger.error(f"Error generating answer: {e}")
            # On error, return fallback to avoid hallucination
            return AnswerResult(
                answer=self.FALLBACK_MESSAGE,
                found_status="NOT_FOUND",
                sources=[],
                is_escalation=False
            )
