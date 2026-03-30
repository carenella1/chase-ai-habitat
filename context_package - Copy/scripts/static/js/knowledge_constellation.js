async function loadConstellation()
{
    const response = await fetch("/api/habitat/status")
    const data = await response.json()

    const container = document.getElementById("constellation")

    const nodes = []
    const edges = []

    let index = 0

    data.recent_activity.forEach(entry =>
    {
        const id = "k_" + index

        nodes.push({
            id:id,
            label:entry.substring(0,35),
            shape:"dot",
            size:16,
            color:{
                background:"#6cf6ff",
                border:"#00eaff"
            },
            font:{
                color:"#d9e6ff",
                size:14
            }
        })

        if(index > 0)
        {
            edges.push({
                from:"k_" + (index - 1),
                to:id,
                color:"#00eaff"
            })
        }

        index++
    })

    const networkData = {
        nodes:new vis.DataSet(nodes),
        edges:new vis.DataSet(edges)
    }

    const options =
    {
        physics:
        {
            enabled:true,
            barnesHut:
            {
                gravitationalConstant:-1800,
                centralGravity:0.1,
                springLength:180,
                springConstant:0.02
            }
        },

        nodes:
        {
            shadow:true
        },

        edges:
        {
            smooth:true
        },

        interaction:
        {
            hover:true
        }
    }

    new vis.Network(container,networkData,options)
}

loadConstellation()
setInterval(loadConstellation,5000)