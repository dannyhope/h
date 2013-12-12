# Abstract anchor class.
class Anchor

  constructor: (@annotator, @annotation, @target
      @startPage, @endPage,
      @quote, @diffHTML, @diffCaseOnly) ->

    unless @annotator? then throw "annotator is required!"
    unless @annotation? then throw "annotation is required!"
    unless @target? then throw "target is required!"
    unless @startPage? then "startPage is required!"
    unless @endPage? then throw "endPage is required!"
    unless @quote? then throw "quote is required!"

    @highlight = {}

  # Return highlights for the given page
  _createHighlight: (page) ->
    throw "Function not implemented"

  # Create the missing highlights for this anchor
  realize: () =>
    return if @fullyRealized # If we have everything, go home

    # Collect the pages that are already rendered
    renderedPages = [@startPage .. @endPage].filter (index) =>
      @annotator.domMapper.isPageMapped index

    # Collect the pages that are already rendered, but not yet anchored
    pagesTodo = renderedPages.filter (index) => not @highlight[index]?

    return unless pagesTodo.length # Return if nothing to do

    try
      # Create the new highlights
      created = for page in pagesTodo
        @highlight[page] = @_createHighlight page

      # Check if everything is rendered now
      @fullyRealized = renderedPages.length is @endPage - @startPage + 1

      # Announce the creation of the highlights
      @annotator.publish 'highlightsCreated', created
    catch error
      console.log "Error while trying to create highlight:", error.stack

      @fullyRealized = false

      # Try to undo the highlights already created
      for page in pagesTodo when @highlight[page]
        try
          @highlight[page].removeFromDocument()
          console.log "Removed LH from page", page
        catch hlError
          console.log "Could not remove HL from page", page, ":", hlError.stack

  # Remove the highlights for the given set of pages
  virtualize: (pageIndex) =>
    highlight = @highlight[pageIndex]

    return unless highlight? # No highlight for this page

    try
      highlight.removeFromDocument()
    catch error
      console.log "Could not remove HL from page", pageIndex, ":", error.stack

    delete @highlight[pageIndex]

    # Mark this anchor as not fully rendered
    @fullyRealized = false

    # Announce the removal of the highlight
    @annotator.publish 'highlightRemoved', highlight

  # Virtualize and remove an anchor from all involved pages,
  # and optionally remove it from the annotation, too
  remove: (removeFromAnnotation = false) ->
    # Go over all the pages
    for index in [@startPage .. @endPage]
      @virtualize index
      anchors = @annotator.anchors[index]
      # Remove the anchor from the list
      Util.removeFromList this, anchors
      # Kill the list if it's empty
      delete @annotator.anchors[index] unless anchors.length

    # Should we remove this anchor from the annotation, too?
    if removeFromAnnotation
      # Remove the anchor from the list
      Util.removeFromList this, @annotation.anchors

  # This is called when the underlying Annotator has been udpated
  annotationUpdated: ->
    # Notify the highlights
    for index in [@startPage .. @endPage]
      @highlight[index]?.annotationUpdated()
