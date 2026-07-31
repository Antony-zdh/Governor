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

  -- Claim audit coloring: supported claims are green, contradicted/unsafe
  -- claims red, and externally pending claims blue. Color the claim, status,
  -- and its evidence/limitation pointer rather than relying on a detached key.
  if first_header == "ID" and #tbl.colspecs == 5 then
    local function color_cell(cell, color)
      for _, block in ipairs(cell.contents) do
        if block.t == "Plain" or block.t == "Para" then
          table.insert(block.content, 1,
            pandoc.RawInline("latex", "\\begingroup\\color{" .. color .. "}"))
          table.insert(block.content,
            pandoc.RawInline("latex", "\\endgroup"))
        end
      end
    end
    for _, row in ipairs(tbl.bodies[1].body) do
      local reliability = pandoc.utils.stringify(row.cells[4].contents)
      local color = "ClaimGreen"
      if reliability:find("未完成") then
        color = "ClaimBlue"
      elseif reliability:find("低") or reliability:find("不支持") then
        color = "ClaimRed"
      end
      for _, index in ipairs({1, 2, 4, 5}) do
        color_cell(row.cells[index], color)
      end
    end
  end
  return tbl
end
