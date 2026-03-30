const canvas = document.createElement("canvas")
canvas.id = "neural-bg"

document.body.appendChild(canvas)

const ctx = canvas.getContext("2d")

let width
let height

let nodes = []

function resize()
{
width = canvas.width = window.innerWidth
height = canvas.height = window.innerHeight
}

window.addEventListener("resize", resize)

resize()

for(let i=0;i<60;i++)
{
nodes.push({
x:Math.random()*width,
y:Math.random()*height,
vx:(Math.random()-0.5)*0.3,
vy:(Math.random()-0.5)*0.3
})
}

function draw()
{
ctx.clearRect(0,0,width,height)

nodes.forEach(n =>
{
n.x += n.vx
n.y += n.vy

if(n.x<0||n.x>width) n.vx*=-1
if(n.y<0||n.y>height) n.vy*=-1

ctx.beginPath()
ctx.arc(n.x,n.y,2,0,Math.PI*2)
ctx.fillStyle="#00eaff"
ctx.fill()
})

for(let i=0;i<nodes.length;i++)
{
for(let j=i+1;j<nodes.length;j++)
{
let dx = nodes[i].x - nodes[j].x
let dy = nodes[i].y - nodes[j].y

let dist = Math.sqrt(dx*dx+dy*dy)

if(dist < 120)
{
ctx.beginPath()
ctx.moveTo(nodes[i].x,nodes[i].y)
ctx.lineTo(nodes[j].x,nodes[j].y)

ctx.strokeStyle = "rgba(0,234,255,"+(1-dist/120)+")"
ctx.stroke()
}
}
}

requestAnimationFrame(draw)
}

draw()