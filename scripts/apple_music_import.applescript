on run argv
    if (count of argv) is 0 then
        return
    end if
    tell application "Music"
        activate
        repeat with f in argv
            try
                add POSIX file f
            end try
        end repeat
    end tell
end run
