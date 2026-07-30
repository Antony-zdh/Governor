-- Stable table widths for the landscape finding-evidence map.
local widths_by_columns = {
  [2] = {0.28, 0.72},
  [3] = {0.16, 0.57, 0.27},
  [4] = {0.16, 0.50, 0.14, 0.20},
  [5] = {0.045, 0.19, 0.405, 0.085, 0.275},
  [6] = {0.12, 0.18, 0.16, 0.16, 0.19, 0.19},
  [7] = {0.16, 0.16, 0.13, 0.14, 0.14, 0.14, 0.13},
}

function Table(tbl)
  local widths = nil
  local first_header = ""
  if tbl.head and tbl.head.rows and tbl.head.rows[1] and tbl.head.rows[1].cells[1] then
    first_header = pandoc.utils.stringify(tbl.head.rows[1].cells[1].contents)
  end

  -- The generic five-column layout is optimized for the main claim matrix.
  -- These appendix audit tables need wider identifier columns to remain readable.
  if first_header == "Named rule" then
    widths = {0.15, 0.13, 0.28, 0.27, 0.17}
  elseif first_header == "Model role" then
    widths = {0.13, 0.20, 0.22, 0.27, 0.18}
  elseif first_header == "Baseline" then
    widths = {0.13, 0.17, 0.34, 0.36}
  elseif first_header == "Seed" then
    widths = {0.08, 0.19, 0.17, 0.28, 0.28}
  elseif first_header == "Method summary" then
    widths = {0.15, 0.18, 0.17, 0.25, 0.25}
  elseif first_header == "Method / w" then
    widths = {0.18, 0.205, 0.205, 0.205, 0.205}
  else
    widths = widths_by_columns[#tbl.colspecs]
  end

  if not widths then
    return tbl
  end
  for index, colspec in ipairs(tbl.colspecs) do
    tbl.colspecs[index] = {colspec[1], widths[index]}
  end
  return tbl
end
