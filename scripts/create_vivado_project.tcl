# Usage:
#   vivado -mode batch -source scripts/create_vivado_project.tcl -tclargs rev_b 35t
#   vivado -mode batch -source scripts/create_vivado_project.tcl -tclargs rev_c 15t
#   vivado -mode batch -source scripts/create_vivado_project.tcl -tclargs rev_b 35t build

set board_revision "rev_b"
set fpga_variant "35t"
set build_bitstream false
if {$argc >= 1} {
    set board_revision [lindex $argv 0]
}
if {$argc >= 2} {
    set fpga_variant [string tolower [lindex $argv 1]]
}
if {$argc >= 3 && [string tolower [lindex $argv 2]] eq "build"} {
    set build_bitstream true
}

set script_dir [file dirname [file normalize [info script]]]
set root_dir [file dirname $script_dir]
set project_dir [file join $root_dir build "vivado_${board_revision}"]

if {$board_revision eq "rev_b"} {
    set input_clock_hz 12000000
    set constraint_file [file join $root_dir constraints cmod_a7_rev_b_12mhz.xdc]
} elseif {$board_revision eq "rev_c"} {
    set input_clock_hz 100000000
    set constraint_file [file join $root_dir constraints cmod_a7_rev_c_100mhz.xdc]
} else {
    error "board revision must be rev_b or rev_c"
}

if {$fpga_variant eq "35t"} {
    set fpga_part xc7a35tcpg236-1
} elseif {$fpga_variant eq "15t"} {
    set fpga_part xc7a15tcpg236-1
} else {
    error "FPGA variant must be 15t or 35t"
}

create_project tadc_cmod_a7 $project_dir -part $fpga_part -force
set_property target_language Verilog [current_project]

add_files [glob [file join $root_dir rtl *.v]]
add_files -fileset constrs_1 $constraint_file
add_files -fileset sim_1 [file join $root_dir sim tb_tadc_cmod_a7_top.v]

set_property top tadc_cmod_a7_top [get_filesets sources_1]
set_property top tb_tadc_cmod_a7_top [get_filesets sim_1]
set_property generic "INPUT_CLOCK_HZ=${input_clock_hz}" [get_filesets sources_1]

update_compile_order -fileset sources_1
update_compile_order -fileset sim_1

puts "Created project: $project_dir"
puts "Board revision: $board_revision"
puts "FPGA variant: $fpga_variant ($fpga_part)"
puts "Input clock: $input_clock_hz Hz"

if {$build_bitstream} {
    launch_runs synth_1 -jobs 4
    wait_on_run synth_1
    if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {
        error "synthesis did not complete"
    }

    launch_runs impl_1 -to_step write_bitstream -jobs 4
    wait_on_run impl_1
    if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {
        error "implementation did not complete"
    }

    set bit_file [file join [get_property DIRECTORY [get_runs impl_1]] tadc_cmod_a7_top.bit]
    puts "Bitstream: $bit_file"
}
