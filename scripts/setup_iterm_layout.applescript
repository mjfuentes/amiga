-- iTerm2 Full Screen 2x2 Layout Setup
-- Creates a full-screen window divided into 4 panes (2 columns x 2 rows)
-- Runs 'agentlab' alias in each pane

tell application "iTerm"
    -- Create new window
    create window with default profile

    tell current window
        tell current session
            -- Split vertically (creates left and right panes)
            set rightPane to (split vertically with default profile)

            -- Split left pane horizontally (creates bottom-left pane)
            set bottomLeftPane to (split horizontally with default profile)

            -- Split right pane horizontally (creates bottom-right pane)
            tell rightPane
                set bottomRightPane to (split horizontally with default profile)
            end tell
        end tell

        -- Enter full screen mode
        tell application "System Events"
            keystroke "f" using {command down, control down}
        end tell

        -- Wait briefly for panes to be ready
        delay 0.5

        -- Run agentlab in all 4 panes
        tell first session
            write text "agentlab"
        end tell

        tell second session
            write text "agentlab"
        end tell

        tell third session
            write text "agentlab"
        end tell

        tell fourth session
            write text "agentlab"
        end tell
    end tell
end tell
