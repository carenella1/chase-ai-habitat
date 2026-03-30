async function loadGraph()
{
    const response = await fetch("/api/habitat/status")
    const data = await response.json()

    const container = document.getElementById("graph")

    const nodes = []
    const edges = []

    let index = 0

    data.recent_activity.forEach(entry =>
    {
        const nodeId = "node_" + index

        nodes.push({
            id: nodeId,
            label: entry.substring(0,40),
            shape: "dot",
            size: 18,
            color:
            {
                background: "#00c3ff",
                border: "#00f0ff",
                highlight:
                {
                    background:"#00f0ff",
                    border:"#66ffff"
                }
            },
            font:
            {
                color:"#d9e6ff",
                size:16
            }
        })

        if(index > 0)
        {
            edges.push({
                from: "node_" + (index - 1),
                to: nodeId,
                color:
                {
                    color:"#00eaff",
                    opacity:0.6
                },
                width:2
            })
        }

        index++
    })

    const networkData =
    {
        nodes: new vis.DataSet(nodes),
        edges: new vis.DataSet(edges)
    }

    const options =
    {
        nodes:
        {
            borderWidth:2,
            shadow:true
        },

        edges:
        {
            smooth:
            {
                type:"dynamic"
            }
        },

        physics:
        {
            enabled:true,
            stabilization:false,
            barnesHut:
            {
                gravitationalConstant:-3000,
                centralGravity:0.2,
                springLength:120,
                springConstant:0.05
            }
        },

        interaction:
        {
            hover:true
        }
    }

    new vis.Network(container, networkData, options)
}

loadGraph()