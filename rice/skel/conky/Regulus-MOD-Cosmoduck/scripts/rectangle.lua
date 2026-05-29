-- rectangle.lua

require 'cairo'

function conky_draw_rect(cr)
    -- Set the rectangle size
    local rect_width = 140
    local rect_height = 140

    -- Set the rectangle position
    local rect_x = 97
    local rect_y = 5

    -- Set the rectangle color to black with 70% transparency (RGBA values in the range of 0 to 1)
    local red, green, blue, alpha = 0, 0, 0, 0.7

    -- Set the line width
    local line_width = 2

    -- Set the rectangle outline color to black with 100% transparency
    local outline_red, outline_green, outline_blue, outline_alpha = 0, 0, 0, 0

    -- Set the corner radius
    local corner_radius = 15

    -- Draw the resized rectangle with rounded corners and transparency
    cairo_set_source_rgba(cr, red, green, blue, alpha)
    cairo_move_to(cr, rect_x + corner_radius, rect_y)
    cairo_line_to(cr, rect_x + rect_width - corner_radius, rect_y)
    cairo_arc(cr, rect_x + rect_width - corner_radius, rect_y + corner_radius, corner_radius, -math.pi / 2, 0)
    cairo_line_to(cr, rect_x + rect_width, rect_y + rect_height - corner_radius)
    cairo_arc(cr, rect_x + rect_width - corner_radius, rect_y + rect_height - corner_radius, corner_radius, 0, math.pi / 2)
    cairo_line_to(cr, rect_x + corner_radius, rect_y + rect_height)
    cairo_arc(cr, rect_x + corner_radius, rect_y + rect_height - corner_radius, corner_radius, math.pi / 2, math.pi)
    cairo_line_to(cr, rect_x, rect_y + corner_radius)
    cairo_arc(cr, rect_x + corner_radius, rect_y + corner_radius, corner_radius, math.pi, -math.pi / 2)
    cairo_close_path(cr)

    cairo_fill(cr)

    -- Draw the rectangle outline with 0% transparency
    cairo_set_source_rgba(cr, outline_red, outline_green, outline_blue, outline_alpha)
    cairo_set_line_width(cr, line_width)
    cairo_move_to(cr, rect_x + corner_radius, rect_y)
    cairo_line_to(cr, rect_x + rect_width - corner_radius, rect_y)
    cairo_arc(cr, rect_x + rect_width - corner_radius, rect_y + corner_radius, corner_radius, -math.pi / 2, 0)
    cairo_line_to(cr, rect_x + rect_width, rect_y + rect_height - corner_radius)
    cairo_arc(cr, rect_x + rect_width - corner_radius, rect_y + rect_height - corner_radius, corner_radius, 0, math.pi / 2)
    cairo_line_to(cr, rect_x + corner_radius, rect_y + rect_height)
    cairo_arc(cr, rect_x + corner_radius, rect_y + rect_height - corner_radius, corner_radius, math.pi / 2, math.pi)
    cairo_line_to(cr, rect_x, rect_y + corner_radius)
    cairo_arc(cr, rect_x + corner_radius, rect_y + corner_radius, corner_radius, math.pi, -math.pi / 2)
    cairo_close_path(cr)

    cairo_stroke(cr)
end

function conky_main()
    if conky_window == nil then
        return
    end

    local cs = cairo_xlib_surface_create(conky_window.display, conky_window.drawable, conky_window.visual, conky_window.width, conky_window.height)
    local cr = cairo_create(cs)

    conky_draw_rect(cr)

    cairo_destroy(cr)
    cairo_surface_destroy(cs)

    return ''
end

-- rectangle.lua

require 'cairo'

function conky_draw_rect(cr)
    -- Set the rectangle size
    local rect_width = 140
    local rect_height = 140

    -- Set the rectangle position
    local rect_x = 97
    local rect_y = 5

    -- Set the rectangle color to black with 70% transparency (RGBA values in the range of 0 to 1)
    local red, green, blue, alpha = 0, 0, 0, 0.7

    -- Set the line width
    local line_width = 2

    -- Set the rectangle outline color to black with 100% transparency
    local outline_red, outline_green, outline_blue, outline_alpha = 0, 0, 0, 0

    -- Set the corner radius
    local corner_radius = 15

    -- Draw the resized rectangle with rounded corners and transparency
    cairo_set_source_rgba(cr, red, green, blue, alpha)
    cairo_move_to(cr, rect_x + corner_radius, rect_y)
    cairo_line_to(cr, rect_x + rect_width - corner_radius, rect_y)
    cairo_arc(cr, rect_x + rect_width - corner_radius, rect_y + corner_radius, corner_radius, -math.pi / 2, 0)
    cairo_line_to(cr, rect_x + rect_width, rect_y + rect_height - corner_radius)
    cairo_arc(cr, rect_x + rect_width - corner_radius, rect_y + rect_height - corner_radius, corner_radius, 0, math.pi / 2)
    cairo_line_to(cr, rect_x + corner_radius, rect_y + rect_height)
    cairo_arc(cr, rect_x + corner_radius, rect_y + rect_height - corner_radius, corner_radius, math.pi / 2, math.pi)
    cairo_line_to(cr, rect_x, rect_y + corner_radius)
    cairo_arc(cr, rect_x + corner_radius, rect_y + corner_radius, corner_radius, math.pi, -math.pi / 2)
    cairo_close_path(cr)

    cairo_fill(cr)

    -- Draw the rectangle outline with 0% transparency
    cairo_set_source_rgba(cr, outline_red, outline_green, outline_blue, outline_alpha)
    cairo_set_line_width(cr, line_width)
    cairo_move_to(cr, rect_x + corner_radius, rect_y)
    cairo_line_to(cr, rect_x + rect_width - corner_radius, rect_y)
    cairo_arc(cr, rect_x + rect_width - corner_radius, rect_y + corner_radius, corner_radius, -math.pi / 2, 0)
    cairo_line_to(cr, rect_x + rect_width, rect_y + rect_height - corner_radius)
    cairo_arc(cr, rect_x + rect_width - corner_radius, rect_y + rect_height - corner_radius, corner_radius, 0, math.pi / 2)
    cairo_line_to(cr, rect_x + corner_radius, rect_y + rect_height)
    cairo_arc(cr, rect_x + corner_radius, rect_y + rect_height - corner_radius, corner_radius, math.pi / 2, math.pi)
    cairo_line_to(cr, rect_x, rect_y + corner_radius)
    cairo_arc(cr, rect_x + corner_radius, rect_y + corner_radius, corner_radius, math.pi, -math.pi / 2)
    cairo_close_path(cr)

    cairo_stroke(cr)
end

function conky_main()
    if conky_window == nil then
        return
    end

    local cs = cairo_xlib_surface_create(conky_window.display, conky_window.drawable, conky_window.visual, conky_window.width, conky_window.height)
    local cr = cairo_create(cs)

    conky_draw_rect(cr)

    cairo_destroy(cr)
    cairo_surface_destroy(cs)

    return ''
end

