-- Headless shim for the `lua-utf8` module PoB requires in Modules/Common.lua.
-- PoB only uses it to place thousands separators in *displayed* numbers; the bridge never reads
-- formatted strings, so byte-wise string functions are sufficient. Not a Unicode implementation.
return {
	gsub = string.gsub,
	find = string.find,
	sub = string.sub,
	reverse = string.reverse,
	match = string.match,
	len = string.len,
	char = string.char,
}
