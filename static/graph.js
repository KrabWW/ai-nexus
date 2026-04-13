// AI Nexus Knowledge Graph Visualization
// D3.js force-directed graph with interactive features

class KnowledgeGraph {
    constructor() {
        this.svg = d3.select("#graph");
        this.width = this.svg.node().getBoundingClientRect().width;
        this.height = this.svg.node().getBoundingClientRect().height;
        this.data = { nodes: [], links: [] };
        this.filteredData = { nodes: [], links: [] };
        this.simulation = null;
        this.currentDomain = "";
        this.currentType = "";
        this.searchQuery = "";
        this.selectedNode = null;

        // Domain colors for entities
        this.domainColors = d3.scaleOrdinal(d3.schemeCategory10);

        this.init();
    }

    async init() {
        // Create group for zoom
        this.g = this.svg.append("g");

        // Setup zoom behavior
        this.zoom = d3.zoom()
            .scaleExtent([0.1, 4])
            .on("zoom", (event) => {
                this.g.attr("transform", event.transform);
            });

        this.svg.call(this.zoom);

        // Create link and node groups
        this.linkGroup = this.g.append("g").attr("class", "links");
        this.nodeGroup = this.g.append("g").attr("class", "nodes");

        // Setup tooltip
        this.tooltip = d3.select("#tooltip");

        // Load data
        await this.loadData();

        // Setup event listeners
        this.setupEventListeners();

        // Populate domain filter
        this.populateDomainFilter();

        // Populate type filter
        this.populateTypeFilter();

        // Initial render
        this.render();
    }

    async loadData() {
        try {
            const response = await fetch("/api/graph/data");
            this.data = await response.json();
            this.filteredData = JSON.parse(JSON.stringify(this.data));
        } catch (error) {
            console.error("Failed to load graph data:", error);
            this.showError();
        }
    }

    setupEventListeners() {
        // Domain filter
        document.getElementById("domainFilter").addEventListener("change", (e) => {
            this.currentDomain = e.target.value;
            this.applyFilters();
        });

        // Type filter
        document.getElementById("typeFilter").addEventListener("change", (e) => {
            this.currentType = e.target.value;
            this.applyFilters();
        });

        // Zoom controls
        document.getElementById("zoomInBtn").addEventListener("click", () => {
            this.svg.transition().call(this.zoom.scaleBy, 1.5);
        });
        document.getElementById("zoomOutBtn").addEventListener("click", () => {
            this.svg.transition().call(this.zoom.scaleBy, 0.67);
        });
        document.getElementById("zoomFitBtn").addEventListener("click", () => {
            this.fitToView();
        });

        // Search input
        document.getElementById("searchInput").addEventListener("input", (e) => {
            this.searchQuery = e.target.value.toLowerCase();
            this.highlightSearchResults();
        });

        // Reset button
        document.getElementById("resetBtn").addEventListener("click", () => {
            this.reset();
        });

        // Close panel
        document.getElementById("closePanel").addEventListener("click", () => {
            this.hideDetailPanel();
        });

        // Window resize
        window.addEventListener("resize", () => {
            this.width = this.svg.node().getBoundingClientRect().width;
            this.height = this.svg.node().getBoundingClientRect().height;
            if (this.simulation) {
                this.simulation.force("center", d3.forceCenter(this.width / 2, this.height / 2));
                this.simulation.alpha(0.3).restart();
            }
        });
    }

    populateDomainFilter() {
        const domains = new Set();
        this.data.nodes.forEach(node => {
            if (node.domain) {
                domains.add(node.domain);
            }
        });

        const select = document.getElementById("domainFilter");
        select.innerHTML = '<option value="">所有域</option>';

        Array.from(domains).sort().forEach(domain => {
            const option = document.createElement("option");
            option.value = domain;
            option.textContent = domain;
            select.appendChild(option);
        });
    }

    filterByDomain() {
        this.applyFilters();
    }

    populateTypeFilter() {
        const types = new Set();
        this.data.nodes.forEach(node => {
            if (node.entity_type) {
                types.add(node.entity_type);
            }
        });

        const select = document.getElementById("typeFilter");
        select.innerHTML = '<option value="">所有类型</option>';

        Array.from(types).sort().forEach(type => {
            const option = document.createElement("option");
            option.value = type;
            option.textContent = type;
            select.appendChild(option);
        });
    }

    applyFilters() {
        // Start with domain filter
        let nodeIds = null;
        if (this.currentDomain) {
            const domainNodes = new Set(
                this.data.nodes
                    .filter(n => n.domain === this.currentDomain)
                    .map(n => n.id)
            );
            const connectedNodes = new Set(domainNodes);
            this.data.links.forEach(link => {
                if (domainNodes.has(link.source) || domainNodes.has(link.target)) {
                    connectedNodes.add(link.source);
                    connectedNodes.add(link.target);
                }
            });
            nodeIds = connectedNodes;
        }

        // Apply type filter on top
        this.filteredData.nodes = this.data.nodes.filter(n => {
            if (nodeIds && !nodeIds.has(n.id)) return false;
            if (this.currentType && n.entity_type !== this.currentType) return false;
            n._crossDomain = nodeIds ? (nodeIds.has(n.id) && !n.domain?.includes(this.currentDomain)) : false;
            return true;
        });

        const filteredIds = new Set(this.filteredData.nodes.map(n => n.id));
        this.filteredData.links = this.data.links.filter(l =>
            filteredIds.has(l.source) && filteredIds.has(l.target)
        );

        this.render();
    }

    fitToView() {
        if (this.filteredData.nodes.length === 0) return;
        const nodes = this.filteredData.nodes;
        let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
        nodes.forEach(n => {
            if (n.x !== undefined) {
                minX = Math.min(minX, n.x);
                maxX = Math.max(maxX, n.x);
                minY = Math.min(minY, n.y);
                maxY = Math.max(maxY, n.y);
            }
        });
        if (minX === Infinity) return;
        const padding = 80;
        const dx = maxX - minX + padding * 2;
        const dy = maxY - minY + padding * 2;
        const scale = Math.min(this.width / dx, this.height / dy, 2);
        const cx = (minX + maxX) / 2;
        const cy = (minY + maxY) / 2;
        const transform = d3.zoomIdentity
            .translate(this.width / 2, this.height / 2)
            .scale(scale)
            .translate(-cx, -cy);
        this.svg.transition().duration(500).call(this.zoom.transform, transform);
    }

    highlightSearchResults() {
        if (!this.searchQuery) {
            this.nodeGroup.selectAll(".node")
                .classed("highlighted", false)
                .classed("dimmed", false);
            return;
        }

        this.nodeGroup.selectAll(".node")
            .classed("dimmed", true)
            .classed("highlighted", d =>
                d.name.toLowerCase().includes(this.searchQuery) ||
                (d.description && d.description.toLowerCase().includes(this.searchQuery))
            );
    }

    reset() {
        this.currentDomain = "";
        this.currentType = "";
        this.searchQuery = "";
        document.getElementById("domainFilter").value = "";
        document.getElementById("typeFilter").value = "";
        document.getElementById("searchInput").value = "";
        this.filteredData = JSON.parse(JSON.stringify(this.data));
        this.hideDetailPanel();
        this.render();
    }

    render() {
        // Clear existing
        this.linkGroup.selectAll("*").remove();
        this.nodeGroup.selectAll("*").remove();

        if (this.filteredData.nodes.length === 0) {
            this.showEmptyState();
            return;
        }

        // Convert links source/target to node references
        const nodeById = new Map(this.filteredData.nodes.map(n => [n.id, n]));
        const links = this.filteredData.links.map(l => ({
            ...l,
            source: nodeById.get(l.source),
            target: nodeById.get(l.target),
        })).filter(l => l.source && l.target);

        // Create simulation
        this.simulation = d3.forceSimulation(this.filteredData.nodes)
            .force("link", d3.forceLink(links).id(d => d.id).distance(100))
            .force("charge", d3.forceManyBody().strength(-300))
            .force("center", d3.forceCenter(this.width / 2, this.height / 2))
            .force("collision", d3.forceCollide().radius(30));

        // Create links
        const link = this.linkGroup.selectAll("line")
            .data(links)
            .join("line")
            .attr("class", "link");

        // Create nodes
        const node = this.nodeGroup.selectAll(".node")
            .data(this.filteredData.nodes)
            .join("g")
            .attr("class", "node")
            .call(this.drag(this.simulation));

        // Node circles
        node.append("circle")
            .attr("r", d => d.type === "rule" ? 20 : 15)
            .attr("opacity", d => d._crossDomain ? 0.3 : 1.0)
            .attr("class", d => {
                if (d.type === "rule") {
                    return `rule-node rule-${d.severity || "info"}`;
                }
                return "entity-node";
            })
            .style("fill", d => {
                if (d.type === "rule") return null; // use CSS class colors
                return this.domainColors(d.domain || "");
            });

        // Node labels
        node.append("text")
            .attr("dy", d => d.type === "rule" ? 30 : 25)
            .text(d => d.name.length > 10 ? d.name.substring(0, 10) + "..." : d.name)
            .attr("fill", "#333")
            .attr("font-size", "11px")
            .attr("opacity", d => d._crossDomain ? 0.3 : 1.0);

        // Node interactions
        node.on("mouseover", (event, d) => this.showTooltip(event, d))
            .on("mouseout", () => this.hideTooltip())
            .on("click", (event, d) => this.showNodeDetails(d));

        // Update simulation on tick
        this.simulation.on("tick", () => {
            link
                .attr("x1", d => d.source.x)
                .attr("y1", d => d.source.y)
                .attr("x2", d => d.target.x)
                .attr("y2", d => d.target.y);

            node.attr("transform", d => `translate(${d.x},${d.y})`);
        });
    }

    drag(simulation) {
        function dragstarted(event, d) {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
        }

        function dragged(event, d) {
            d.fx = event.x;
            d.fy = event.y;
        }

        function dragended(event, d) {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
        }

        return d3.drag()
            .on("start", dragstarted)
            .on("drag", dragged)
            .on("end", dragended);
    }

    showTooltip(event, d) {
        this.tooltip
            .classed("visible", true)
            .html(`
                <div class="tooltip-title">${d.name}</div>
                <div class="tooltip-type">${d.type === "rule" ? "规则" : "实体"}</div>
                ${d.domain ? `<span class="tooltip-domain">${d.domain}</span>` : ""}
                ${d.description ? `<div style="margin-top: 0.5rem">${d.description.substring(0, 100)}${d.description.length > 100 ? "..." : ""}</div>` : ""}
            `)
            .style("left", (event.pageX + 15) + "px")
            .style("top", (event.pageY - 10) + "px");
    }

    hideTooltip() {
        this.tooltip.classed("visible", false);
    }

    showNodeDetails(d) {
        const panel = document.getElementById("detailPanel");
        const content = document.getElementById("panelContent");

        if (d.type === "rule") {
            content.innerHTML = this.renderRuleDetails(d);
        } else {
            content.innerHTML = this.renderEntityDetails(d);
        }

        panel.classList.remove("hidden");
        panel.classList.add("visible");
    }

    renderEntityDetails(entity) {
        const attributes = entity.attributes || {};
        const attrsHtml = Object.entries(attributes).map(([key, value]) => `
            <div class="attribute-row">
                <span class="attribute-key">${key}</span>
                <span class="attribute-value">${value}</span>
            </div>
        `).join("");

        return `
            <div class="panel-header">
                <div class="panel-title">${entity.name}</div>
                <span class="panel-domain">${entity.domain || "未分类"}</span>
            </div>

            ${entity.description ? `
                <div class="panel-section">
                    <div class="panel-section-title">描述</div>
                    <div class="panel-description">${entity.description}</div>
                </div>
            ` : ""}

            ${Object.keys(attributes).length > 0 ? `
                <div class="panel-section">
                    <div class="panel-section-title">属性</div>
                    <div class="panel-attributes">${attrsHtml}</div>
                </div>
            ` : ""}

            <div class="panel-section">
                <div class="panel-section-title">类型</div>
                <div class="panel-description">${entity.type}</div>
            </div>

            <div class="panel-section">
                <div class="panel-section-title">状态</div>
                <span class="severity-badge severity-info">${entity.status || "unknown"}</span>
            </div>
        `;
    }

    renderRuleDetails(rule) {
        const severityClass = `severity-${rule.severity || "info"}`;

        return `
            <div class="panel-header">
                <div class="panel-title">${rule.name}</div>
                <span class="panel-domain">${rule.domain || "未分类"}</span>
            </div>

            <div class="panel-section">
                <div class="panel-section-title">严重程度</div>
                <span class="severity-badge ${severityClass}">${rule.severity || "info"}</span>
            </div>

            ${rule.description ? `
                <div class="panel-section">
                    <div class="panel-section-title">规则描述</div>
                    <div class="panel-description">${rule.description}</div>
                </div>
            ` : ""}

            ${rule.conditions ? `
                <div class="panel-section">
                    <div class="panel-section-title">条件</div>
                    <div class="panel-description">
                        <pre style="white-space: pre-wrap; font-size: 0.85rem;">${JSON.stringify(rule.conditions, null, 2)}</pre>
                    </div>
                </div>
            ` : ""}

            <div class="panel-section">
                <div class="panel-section-title">状态</div>
                <span class="severity-badge severity-info">${rule.status || "pending"}</span>
            </div>

            ${rule.confidence !== undefined ? `
                <div class="panel-section">
                    <div class="panel-section-title">置信度</div>
                    <div class="panel-description">${(rule.confidence * 100).toFixed(1)}%</div>
                </div>
            ` : ""}

            <div class="panel-section">
                <div class="panel-section-title">来源</div>
                <div class="panel-description">${rule.source || "unknown"}</div>
            </div>
        `;
    }

    hideDetailPanel() {
        const panel = document.getElementById("detailPanel");
        panel.classList.remove("visible");
        panel.classList.add("hidden");
    }

    showEmptyState() {
        this.g.append("text")
            .attr("x", this.width / 2)
            .attr("y", this.height / 2)
            .attr("text-anchor", "middle")
            .attr("fill", "#999")
            .attr("font-size", "1.2rem")
            .text("暂无数据");
    }

    showError() {
        this.g.append("text")
            .attr("x", this.width / 2)
            .attr("y", this.height / 2)
            .attr("text-anchor", "middle")
            .attr("fill", "#ef4444")
            .attr("font-size", "1.2rem")
            .text("加载失败，请刷新页面重试");
    }
}

// Initialize graph when DOM is ready
document.addEventListener("DOMContentLoaded", () => {
    new KnowledgeGraph();
});
