# TO-DO: Host on AWS/Azure


# Imports
import os
import uuid

from dotenv import load_dotenv

import pinecone
from pinecone import Pinecone, ServerlessSpec

from langchain_openai import ChatOpenAI
from langchain_openai import OpenAIEmbeddings

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, MessagesState, StateGraph

import streamlit as st


load_dotenv()
spec = ServerlessSpec(cloud="aws", region="us-east-1") # spec instance
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY")) # pinecone object


# Accessing Indices on pinecone
index_name = "courses-ds" 
index = pc.Index(index_name)

# embedding model
embedding_model = OpenAIEmbeddings(api_key=os.getenv("OPENAI_API_KEY")) # load.env

# function to retrieve relevant chunks from pinecone vector database
def retrieve_from_pinecone(query, top_k=10): # top_k indicates how many chunks we want to retrive from database
    query_embedding = embedding_model.embed_query(query)
    results = index.query(vector=[query_embedding], top_k=top_k, include_metadata=True) # querying database for 10 relevant chunks
    
    relevant_chunks = [match["metadata"].get("text") for match in results["matches"]] 

    # Returning relevant chunks
    return relevant_chunks

# llm instance
llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.3,  # Experiment with different Temperatures
)

# Variable storing how many messages (10) will be remembered (Human + Bot): For conversationalness
memory_messages = 10 # Update to change context lengths

# Converting query to a prompt that has context from the documents
def query_to_prompt(query, state_messages):
    relevant_chunks = retrieve_from_pinecone(query) # retrieveing relevant chunks to make context
    context = "\n\n -------------- \n\n".join(chunk for chunk in relevant_chunks)
    context = f"\n\nCONTEXT: {context}"
    
    # Play around with this.
    sys_message_template = (
        "You are a helpful chatbot specialising in answering questions on the Data Science discipline at Krea. You are required to understand sensitive information such as passwords, email id's and phone numbers and not share such information with users."
        "Do not hallucinate any answers; if you do not understand the question, ask the user to describe what they would like. If you do not have the required information or do not know how to answer the question, tell the user in this format: 'I currently do not have the information to answer that question, I am trained on the data provided in October 2023. If you would like to know more about more recent updates, you may email the academic office at Krea. academicoffice@krea.edu.in'"
        "If the user asks for specific information from a particular department, respectfully provide the data. For student life-related questions, refer the user to the office of student life. For academic questions, refer the user to the academic office. For administrative questions, refer the user to the Krea administration point of contact."
        "While answering a question, be sure to recheck the data for relevant information. Be verbose with your answers. Make sure you understand dependencies between courses. For example, if the user is asking for the prerequisites for a course C is B and the prerequisite for course B is A. Then, if you are asked for the prerequisites for course C, make sure to mention all the prerequisites, both A and B since it is not possible to do the courses without the required prerequisites. For any additional queries regarding prerequisites, refer the user to contact the academic office or the concerned professor since the waivers are given on a case by case basis."
        "Understand that most users are students, so aim to explain answers in a simple and effective way to make it easier to understand."
        "Do not entertain any questions regarding phone numbers and personal information on professors or members of the Krea faculty."
        "Only answer questions related to the data science dicipline. If asked about any other subject, ask the user to contact the academic office" # Update this if we are going to go ahead and extend this to multiple disciplines
        "Do not make up relavancy, only mention cross listed courses if they are actually cross listed. Do not come up with your own correlations between courses"
        "The CONTEXT is as follows:\n{}"
    )
    formatted_sys_message = SystemMessage(sys_message_template.format(context))
    
    # Remove any existing SystemMessage from state_messages
    messages = [msg for msg in state_messages if not isinstance(msg, SystemMessage)]
    
    # Start with the last 'memory_messages' messages from the state
    if len(messages) > memory_messages - 1:
        messages = messages[-(memory_messages - 1):]  # Reserve one spot for SystemMessage
    
    # Insert the new SystemMessage at the beginning
    messages.insert(0, formatted_sys_message)
    
    # Add the current user query
    messages.append(HumanMessage(content=query))
    
    return {"messages": messages} # returning the prompt

# Function to call Rag Model
def call_rag_model(state: MessagesState):
    response = llm.invoke(state["messages"])
    
    # Update the state with the new response
    state["messages"].append(response)
    
    # Keep only the last few messages in the state
    if len(state["messages"]) > memory_messages:
        state["messages"] = state["messages"][-1 * (memory_messages):] # Update this for more context
    
    # Maybe limit the context to say 1k tokens?? Maybe use an LLM or to summarise contexts?
    
    return {"messages": state["messages"]}

# New StageGraph from LangGraph for memory
workflow = StateGraph(state_schema=MessagesState)

workflow.add_edge(START, "model")
workflow.add_node("model", call_rag_model)

memory = MemorySaver()
app = workflow.compile(checkpointer=memory)

# uuid for thread_id for configurable 
thread_id = str(uuid.uuid4())
config = {"configurable": {"thread_id": thread_id}}
#print(thread_id) 

# Getting response from llm
def get_response(query, state):
    input_data = query_to_prompt(query, state["messages"])
    output = app.invoke(input_data, config)

    # updating state history
    state["messages"] = output["messages"] 

    llm_response = output["messages"][-1].content

    return llm_response, state

# Title of Webpage
st.title("RAG BOT") # Change this

# Captioning Page
st.caption("As this chatbot is built on an LLM, it can make mistakes. Contact discipline co-ordinator if doubts persist.")

# Creating section for example prompts
st.markdown("""-----------------------------------------------------""")

# Opening Questions.txt
with open ("Questions.txt", "r") as f:
    sample_questions = f.read().split("\n\n")

i,j,k = nprand.randint(0, len(sample_questions) -1 , 3) # Random Numbers to determine Questions

# Displaying Example Prompts
st.markdown("""###### Example Prompts""")
st.markdown(f"""
* {sample_questions[i]}
* {sample_questions[j]}
* {sample_questions[k]}
""")
st.markdown("""-----------------------------------------------------""")

# Chat window section
st.markdown("""### Chat Window""")

# tracking history of session state
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Hello! I am a chatbot to help with all your Data Science curriculum related queries. How can I help you?"}] # Initial message

# To display Chat History:
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

# Initialising state
if "state_messages" not in st.session_state:
    st.session_state.state_messages = []

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Hello! I am a chatbot to help with all your curriculum-related queries. How can I help you?"}
    ]


state = {"messages": st.session_state.state_messages}


# Secrets file for api keys 

# For Streaming: To be done later
def message_generator(message_content):
    for chunk in message_content.split(". "):  # Splitting by sentence
        yield chunk + ".\n"


query = st.chat_input("Enter your queries here: ")
if query is not None and query != "":
    st.session_state.messages.append({"role": "user", "content": query})

    # Initial input
    with st.chat_message("user"):
        st.write(query)

    # Getting Response from Conversational RAG
    llm_response, state = get_response(query, state)

    # Updating session history
    st.session_state.state_messages = state["messages"]
    st.session_state.messages.append({"role": "assistant", "content": llm_response})

    # Displaying chatbot output
    with st.chat_message("assistant"):
        st.write(llm_response)
        # For Streaming
        #st.write_stream(message_generator(llm_response))
