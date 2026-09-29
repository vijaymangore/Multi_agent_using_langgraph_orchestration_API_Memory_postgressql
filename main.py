import os
from typing import TypedDict, Annotated
import operator

import psycopg
from psycopg_pool import ConnectionPool
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver

from langchain_core.messages import (
    AnyMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
)
from langchain_groq import ChatGroq

from Tools.Tavily_tool import tavily_search
from Tools.flight_tool import search_flights
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
key=os.getenv("GROQ_API_KEY")

# Active Groq models
primary_llm = ChatGroq(
    model="'openai/gpt-oss-safeguard-20b",
    api_key=os.getenv("GROQ_API_KEY"),
    temperature=0.7,
)

fallback_llm_1 = ChatGroq(
    model='openai/gpt-oss-120b',
    api_key=os.getenv("GROQ_API_KEY"),
    temperature=0.7,
)

fallback_llm_2 = ChatGroq(
    model="qwen-2.5-72b-instruct",
    api_key=os.getenv("GROQ_API_KEY"),
    temperature=0.7,
)

# Automatically switch to fallbacks if rate-limited or unavailable
llm = primary_llm.with_fallbacks([fallback_llm_1, fallback_llm_2])


# # LLM setup using standard Groq model
# llm = ChatGroq(
#     model="llama-3.1-8b-instant",api_key=key
# )

# State definition
class TravelState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    user_query: str
    flight_results: str
    hotel_results: str
    itinerary: str
    llm_calls: int


# Flight Agent
def flight_agent(state: TravelState):
    query = state.get("user_query", "")
    flight_data = search_flights(query)
    return {
        "flight_results": str(flight_data),
        "messages": [AIMessage(content="Flight results fetched.")],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


# Hotel Agent
def hotel_agent(state: TravelState):
    query = f"Best hotels for {state.get('user_query', '')}"
    hotel_results = tavily_search(query)

    return {
        "hotel_results": str(hotel_results),
        "messages": [AIMessage(content="Hotel information fetched.")],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


# Itinerary Agent
def itinerary_agent(state: TravelState):
    prompt = f"""
    Create a travel itinerary.
    User Query:
    {state.get('user_query', '')}

    Flight Results:
    {state.get('flight_results', '')}

    Hotel Results:
    {state.get('hotel_results', '')}
    """

    response = llm.invoke(
        [
            SystemMessage(content="You are an expert travel planner."),
            HumanMessage(content=prompt),
        ]
    )

    return {
        "itinerary": response.content,
        "messages": [response],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


# Final Response Agent
def final_agent(state: TravelState):
    final_prompt = f"""
    Generate final travel response summarizing options concisely.

    Flights:
    {state.get('flight_results', '')}

    Hotels:
    {state.get('hotel_results', '')}

    Itinerary:
    {state.get('itinerary', '')}
    """

    response = llm.invoke([HumanMessage(content=final_prompt)])

    return {
        "messages": [response],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


# Define LangGraph graph
graph = StateGraph(TravelState)

graph.add_node("flight_agent", flight_agent)
graph.add_node("hotel_agent", hotel_agent)
graph.add_node("itinerary_agent", itinerary_agent)
graph.add_node("final_agent", final_agent)

graph.add_edge(START, "flight_agent")
graph.add_edge("flight_agent", "hotel_agent")
graph.add_edge("hotel_agent", "itinerary_agent")
graph.add_edge("itinerary_agent", "final_agent")
graph.add_edge("final_agent", END)


# Connection pooling setup for PostgreSQL Checkpointer
connection_kwargs = {
    "autocommit": True,
    "prepare_threshold": 0,
}

# 1. Use ConnectionPool for stable PostgreSQL checkpointing

# Create connection pool
pool = ConnectionPool(
    conninfo=DATABASE_URL,
    max_size=20,
    kwargs=connection_kwargs,
)

checkpointer = PostgresSaver(pool)
checkpointer.setup()

app = graph.compile(checkpointer=checkpointer)

if __name__ == "__main__":
    try:
        config = {"configurable": {"thread_id": "user_Vijay"}}
        user_input = input("Enter travel request: ")

        result = app.invoke(
            {
                "messages": [HumanMessage(content=user_input)],
                "user_query": user_input,
                "flight_results": "",
                "hotel_results": "",
                "itinerary": "",
                "llm_calls": 0,
            },
            config=config,
        )

        print("\nFINAL RESPONSE:\n")
        if result.get("messages"):
            print(result["messages"][-1].content)
    finally:
        pool.close()  # Clean up connection pool on exit


if __name__ == "__main__":
    config = {
        "configurable": {
            "thread_id": "user_aarohi"
        }
    }

    user_input = input("Enter travel request: ")

    result = app.invoke(
        {
            "messages": [HumanMessage(content=user_input)],
            "user_query": user_input,
            "flight_results": "",
            "hotel_results": "",
            "itinerary": "",
            "llm_calls": 0,
        },
        config=config,
    )

    print("\nFINAL RESPONSE:\n")
    
    # Print the final LLM summary message
    if result.get("messages"):
        print(result["messages"][-1].content)