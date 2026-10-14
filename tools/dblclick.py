import sys,time; sys.path.insert(0,'tools'); import harness as H
inst,x,y=sys.argv[1],int(sys.argv[2]),int(sys.argv[3])
pid=H.load_state()[inst]; hw=H.main_window(pid)
H.set_cursor(pid,x,y); time.sleep(0.2)
cx,cy=H.game2client(hw,x,y)
H.user32.PostMessageW(hw,0x200,0,H.lparam(cx,cy)); time.sleep(0.05)
H.user32.PostMessageW(hw,0x201,1,H.lparam(cx,cy)); time.sleep(0.05); H.user32.PostMessageW(hw,0x202,0,H.lparam(cx,cy))
time.sleep(0.08)
H.user32.PostMessageW(hw,0x203,1,H.lparam(cx,cy)); time.sleep(0.05); H.user32.PostMessageW(hw,0x202,0,H.lparam(cx,cy))
