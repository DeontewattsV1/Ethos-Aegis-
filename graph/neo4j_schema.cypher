// Constraints

CREATE CONSTRAINT graph_node_id IF NOT EXISTS
FOR (n:GraphNode)
REQUIRE n.id IS UNIQUE;


// Governance Nodes

CREATE CONSTRAINT governance_name IF NOT EXISTS
FOR (n:Governance)
REQUIRE n.name IS UNIQUE;


// Agent Nodes

CREATE CONSTRAINT agent_name IF NOT EXISTS
FOR (n:Agent)
REQUIRE n.name IS UNIQUE;


// Workflow Nodes

CREATE CONSTRAINT workflow_name IF NOT EXISTS
FOR (n:Workflow)
REQUIRE n.name IS UNIQUE;


// Task Nodes

CREATE CONSTRAINT task_id IF NOT EXISTS
FOR (n:Task)
REQUIRE n.id IS UNIQUE;


// Indexes

CREATE INDEX node_type_index IF NOT EXISTS
FOR (n:GraphNode)
ON (n.node_type);


CREATE INDEX task_status_index IF NOT EXISTS
FOR (n:Task)
ON (n.status);
