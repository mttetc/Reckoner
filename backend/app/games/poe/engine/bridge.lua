-- Reckoner ↔ Path of Building headless bridge.
--
-- Runs inside LuaJIT with the working directory set to PoB's `src/`. Loads PoB through its own
-- HeadlessWrapper.lua, then serves newline-delimited JSON requests on stdin and answers on stdout.
-- Every number returned here is computed by PoB itself; this file only moves data around and
-- refuses modifications PoB cannot honour (unknown node, unreachable node, unknown config value).
--
-- Request:  {"id": 1, "op": "load", "xml": "<PathOfBuilding>…"}
-- Response: {"id": 1, "ok": true, "result": {…}}   or   {"id": 1, "ok": false, "error": "…"}
--
-- Ops: info · load · stats · modify · export · quit

local stdout = io.stdout
local stderr = io.stderr

-- PoB prints progress to stdout; that would corrupt the protocol. Route all of it to stderr.
print = function(...)
	local parts = {}
	for i = 1, select("#", ...) do parts[i] = tostring(select(i, ...)) end
	stderr:write(table.concat(parts, "\t"), "\n")
end

dofile("HeadlessWrapper.lua")

local json = require("dkjson")
local varList = require("Modules.ConfigOptions")

local configVars = {}
for _, v in ipairs(varList) do
	if v.var then configVars[v.var] = v end
end

local state = { xml = nil }

local function respond(id, ok, payload)
	local msg = { id = id, ok = ok }
	if ok then msg.result = payload else msg.error = payload end
	stdout:write(json.encode(msg), "\n")
	stdout:flush()
end

local function recompute()
	build.buildFlag = true
	runCallback("OnFrame")
end

local function isFinite(n)
	return type(n) == "number" and n == n and n ~= math.huge and n ~= -math.huge
end

local function numericFields(tbl)
	local out = {}
	if type(tbl) ~= "table" then return out end
	for k, v in pairs(tbl) do
		if type(k) == "string" and isFinite(v) then out[k] = v end
	end
	return out
end

local function stats()
	local o = build.calcsTab.mainOutput or {}
	local mainSkill = build.calcsTab.mainEnv and build.calcsTab.mainEnv.player.mainSkill
	local allocated, ascendancy = build.spec:CountAllocNodes()
	return {
		player = numericFields(o),
		minion = numericFields(o.Minion),
		main_skill = mainSkill and mainSkill.activeEffect.grantedEffect.name or json.null,
		tree_version = build.spec.treeVersion,
		allocated_nodes = allocated,
		allocated_ascendancy_nodes = ascendancy,
		class_name = build.spec.curClassName,
		ascend_class_name = build.spec.curAscendClassName,
	}
end

local function info()
	return {
		engine = "Path of Building",
		engine_version = launch and launch.versionNumber or json.null,
		latest_tree_version = latestTreeVersion,
		source_commit = os.getenv("POB_SOURCE_COMMIT") or json.null,
		modification_kinds = { "tree.allocate", "tree.deallocate", "config.set", "gem.set_level", "gem.set_quality" },
	}
end

local function loadXml(xml)
	if type(xml) ~= "string" or #xml == 0 then error("xml must be a non-empty string", 0) end
	loadBuildFromXML(xml, "reckoner")
	if not build or not build.spec then error("PoB did not produce a build from this XML", 0) end
	state.xml = xml
end

-- ---------------------------------------------------------------- modifications

local function nodeById(id)
	local n = tonumber(id)
	if not n then error("payload.node_id must be a number", 0) end
	local node = build.spec.nodes[n]
	if not node then error("unknown passive node id " .. n .. " in tree " .. tostring(build.spec.treeVersion), 0) end
	return node
end

local function applyTreeAllocate(p)
	local node = nodeById(p.node_id)
	if node.alloc then return { node_id = node.id, name = node.dn, already_allocated = true } end
	if not node.path then
		error(string.format("node %d (%s) is not reachable from the allocated tree", node.id, tostring(node.dn)), 0)
	end
	local pathIds = {}
	for _, pn in ipairs(node.path) do pathIds[#pathIds + 1] = pn.id end
	build.spec:AllocNode(node)
	return { node_id = node.id, name = node.dn, allocated_path = pathIds }
end

local function applyTreeDeallocate(p)
	local node = nodeById(p.node_id)
	if not node.alloc then error(string.format("node %d (%s) is not allocated", node.id, tostring(node.dn)), 0) end
	if node.type == "ClassStart" or node.type == "AscendClassStart" then
		error("cannot deallocate a class start node", 0)
	end
	local removed = {}
	for _, dep in ipairs(node.depends or {}) do removed[#removed + 1] = dep.id end
	build.spec:DeallocNode(node)
	return { node_id = node.id, name = node.dn, deallocated = removed }
end

local function applyConfigSet(p)
	local var = configVars[p.name]
	if not var then error("unknown config variable '" .. tostring(p.name) .. "'", 0) end
	local value = p.value
	if var.type == "list" then
		local canonical
		for _, opt in ipairs(var.list or {}) do
			if opt.val == value or (type(value) == "string" and type(opt.val) == "string" and opt.val:lower() == value:lower()) then
				canonical = opt.val
			end
		end
		if canonical == nil then
			local allowed = {}
			for _, opt in ipairs(var.list or {}) do allowed[#allowed + 1] = tostring(opt.val) end
			error(string.format("'%s' is not a valid value for %s (allowed: %s)", tostring(value), p.name, table.concat(allowed, ", ")), 0)
		end
		value = canonical
	elseif var.type == "check" then
		if type(value) ~= "boolean" then error(p.name .. " expects a boolean", 0) end
		if value == false then value = nil end
	elseif var.type == "count" or var.type == "integer" or var.type == "countAllowZero" then
		if type(value) ~= "number" then error(p.name .. " expects a number", 0) end
	elseif var.type == "text" then
		if value ~= nil and type(value) ~= "string" then error(p.name .. " expects a string", 0) end
	end
	local previous = build.configTab.input[p.name]
	build.configTab.input[p.name] = value
	build.configTab:BuildModList()
	return { name = p.name, previous = previous == nil and json.null or previous, value = value == nil and json.null or value }
end

local function findGem(p)
	local groupIndex = tonumber(p.group) or build.mainSocketGroup
	local group = build.skillsTab.socketGroupList[groupIndex]
	if not group then error("no socket group at index " .. tostring(groupIndex), 0) end
	for _, gem in ipairs(group.gemList) do
		if gem.nameSpec == p.gem or (gem.gemData and gem.gemData.name == p.gem) then return group, gem end
	end
	error(string.format("gem '%s' not found in socket group %d", tostring(p.gem), groupIndex), 0)
end

local function applyGemLevel(p)
	local group, gem = findGem(p)
	local level = tonumber(p.level)
	if not level or level < 1 or level > 40 then error("level must be a number between 1 and 40", 0) end
	local previous = gem.level
	gem.level = level
	build.skillsTab:ProcessSocketGroup(group)
	return { gem = gem.nameSpec, previous = previous, level = level }
end

local function applyGemQuality(p)
	local group, gem = findGem(p)
	local quality = tonumber(p.quality)
	if not quality or quality < 0 or quality > 100 then error("quality must be a number between 0 and 100", 0) end
	local previous = gem.quality
	gem.quality = quality
	build.skillsTab:ProcessSocketGroup(group)
	return { gem = gem.nameSpec, previous = previous, quality = quality }
end

local appliers = {
	["tree.allocate"] = applyTreeAllocate,
	["tree.deallocate"] = applyTreeDeallocate,
	["config.set"] = applyConfigSet,
	["gem.set_level"] = applyGemLevel,
	["gem.set_quality"] = applyGemQuality,
}

local function modify(mods)
	if not state.xml then error("no build loaded; call load first", 0) end
	if type(mods) ~= "table" then error("modifications must be a list", 0) end
	local applied = {}
	for i, m in ipairs(mods) do
		local fn = appliers[m.kind]
		if not fn then error(string.format("modification %d: unsupported kind '%s'", i, tostring(m.kind)), 0) end
		local ok, res = pcall(fn, m.payload or {})
		if not ok then error(string.format("modification %d (%s): %s", i, m.kind, tostring(res)), 0) end
		res.kind = m.kind
		applied[#applied + 1] = res
	end
	recompute()
	return { applied = applied, stats = stats(), xml = build:SaveDB("code") }
end

-- ---------------------------------------------------------------- tree geometry

-- Geometry of a whole passive tree version, as PoB computes it (group + orbit → x/y). Only the
-- data needed to draw it: no stats, no sprites. Cluster-jewel proxy templates are skipped.
local function treeGeometry(version)
	if type(version) ~= "string" or not version:match("^%d+_%d+$") then
		error("version must look like 3_29", 0)
	end
	local ok, tree = pcall(function() return __mainObject__.main:LoadTree(version) end)
	if not ok or not tree then error("tree version " .. version .. " is not available in this PoB checkout", 0) end
	local nodes, groups, n = {}, {}, 0
	for id, node in pairs(tree.nodes) do
		if node.x and node.y and not node.isProxy then
			local linked = {}
			for _, otherId in ipairs(node.linkedId or {}) do
				local other = tree.nodes[otherId]
				if other and other.x and not other.isProxy then linked[#linked + 1] = otherId end
			end
			n = n + 1
			nodes[n] = {
				id = node.id,
				name = node.dn or node.name or "",
				type = node.type,
				x = math.floor(node.x + 0.5),
				y = math.floor(node.y + 0.5),
				g = node.g,
				o = node.o,
				angle = node.angle,
				ascendancy = node.ascendancyName or json.null,
				class_start = node.classStartIndex or json.null,
				linked = linked,
			}
			if node.group and node.g and not groups[tostring(node.g)] then
				groups[tostring(node.g)] = { x = math.floor(node.group.x + 0.5), y = math.floor(node.group.y + 0.5) }
			end
		end
	end
	return {
		version = version,
		orbit_radii = tree.orbitRadii,
		groups = groups,
		nodes = nodes,
		classes = (function()
			local out = {}
			for i, class in ipairs(tree.classes or {}) do
				local ascs = {}
				for j, a in ipairs(class.classes or {}) do ascs[j] = a.name end
				out[i] = { name = class.name, ascendancies = ascs }
			end
			return out
		end)(),
	}
end

-- ---------------------------------------------------------------- main loop

local ops = {
	info = function() return info() end,
	load = function(req) loadXml(req.xml); return stats() end,
	stats = function() if not state.xml then error("no build loaded", 0) end return stats() end,
	modify = function(req) return modify(req.modifications) end,
	export = function() if not state.xml then error("no build loaded", 0) end return { xml = build:SaveDB("code") } end,
	tree = function(req) return treeGeometry(req.version) end,
}

stdout:write(json.encode({ event = "ready", info = info() }), "\n")
stdout:flush()

for line in io.stdin:lines() do
	if #line > 0 then
		local req, _, decodeErr = json.decode(line)
		if not req then
			respond(json.null, false, "invalid JSON: " .. tostring(decodeErr))
		elseif req.op == "quit" then
			respond(req.id, true, { bye = true })
			break
		else
			local fn = ops[req.op]
			if not fn then
				respond(req.id, false, "unknown op '" .. tostring(req.op) .. "'")
			else
				local ok, res = pcall(fn, req)
				if ok then respond(req.id, true, res) else respond(req.id, false, tostring(res)) end
			end
		end
	end
end
